import hashlib
import json
import logging
import os
import re
import threading
import time
from urllib.parse import quote_from_bytes
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from icalendar import Alarm, Calendar, Event, vText
from pyrinium import Pyrinium

log = logging.getLogger("schedule-parser")

# Документация FastAPI (/docs, /openapi.json) наружу не нужна
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def raw_query_from_nginx(request, call_next):
    # uvicorn отклоняет адреса с кириллицей без %-кодирования (?group=К0609-24),
    # поэтому nginx передаёт строку запроса в заголовке X-Query, а здесь она кодируется
    raw = next((v for k, v in request.scope["headers"] if k == b"x-query"), None)
    if raw is not None:
        request.scope["query_string"] = quote_from_bytes(raw, safe="=&%+/").encode()
    return await call_next(request)

TZ = ZoneInfo("Europe/Moscow")
DEFAULT_GROUP = os.getenv("TARGET_GROUP", "К0609-24")
# Текущая неделя + столько недель вперёд. Если расписания ещё нет, недели просто пустые
WEEKS_AHEAD = int(os.getenv("WEEKS_AHEAD", "2"))
# Как долго отдаём расписание из кэша, не обращаясь к сайту
CACHE_TTL = int(os.getenv("CACHE_TTL", "900"))
# Если сайт недоступен, отдаём последнее удачное расписание не старше этого срока
STALE_MAX_AGE = int(os.getenv("STALE_MAX_AGE", str(7 * 24 * 3600)))
# За сколько минут до пары напоминать. 0 — без напоминаний
ALARM_MINUTES = int(os.getenv("ALARM_MINUTES", "10"))
STATE_DIR = Path(os.getenv("STATE_DIRECTORY", "/var/lib/schedule-parser"))

GROUP_RE = re.compile(r"^[А-ЯЁ]{1,3}\d{3,4}-\d{2}(/\d{1,2})?$")
# Латинские буквы, похожие на кириллические: K0609-24 и К0609-24 — одна группа
LATIN_TO_CYRILLIC = str.maketrans("ABCEHKMOPTXY", "АВСЕНКМОРТХУ")
# ПА / ППА / ППА1 / ПА-2 / (ПА) как отдельное слово, а также «промежуточная аттестация»
PA_RE = re.compile(
    r"(?<![А-Яа-яЁёA-Za-z])П?ПА(?:\s*-?\s*\d+)?(?![А-Яа-яЁёA-Za-z])|промежуточн\w*\s+аттестац",
    re.IGNORECASE,
)

_cache = {}
_locks = {}
_locks_guard = threading.Lock()


def is_pa(item):
    text = " ".join(str(item.get(k) or "") for k in ("discipline", "comment"))
    return bool(PA_RE.search(text))


def format_location(item):
    raw_loc = item.get("classroom") or item.get("place")
    if not raw_loc:
        return "Место не указано"

    clean_loc = re.sub(r"(.{5,}?)\1", r"\1", raw_loc)
    clean_loc = re.sub(r"^[-\d\.\,\s]+", "", clean_loc).strip()
    clean_loc = re.sub(r"^К_(?![0-9])", "", clean_loc).strip()

    return clean_loc or raw_loc


def fetch_events(group):
    c = Pyrinium()
    c.get_initial_data()

    events = []
    for week in range(WEEKS_AHEAD + 1):
        if week:
            c.change_week(1)
        data = c.get_schedule(group)
        if not isinstance(data, dict) or not isinstance(data.get("events"), list):
            raise ValueError(f"unexpected response for week {week}")
        events += data["events"]
    return events


def _state_file(group):
    return STATE_DIR / (hashlib.sha1(group.encode()).hexdigest()[:16] + ".json")


def _load_state(group):
    try:
        saved = json.loads(_state_file(group).read_text())
        return saved["fetched_at"], saved["events"]
    except Exception:
        return None


def _save_state(group, fetched_at, events):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _state_file(group).with_suffix(".tmp")
        tmp.write_text(json.dumps({"fetched_at": fetched_at, "events": events}, ensure_ascii=False))
        tmp.replace(_state_file(group))
    except Exception:
        log.exception("cannot save cache for %s", group)


def get_events(group):
    with _locks_guard:
        lock = _locks.setdefault(group, threading.Lock())

    # Один запрос к сайту на группу одновременно, остальные ждут его результат
    with lock:
        cached = _cache.get(group) or _load_state(group)
        if cached and time.time() - cached[0] < CACHE_TTL:
            return cached[1]

        try:
            events = fetch_events(group)
        except Exception:
            log.exception("fetch failed for %s", group)
            # Пустой календарь стёр бы у подписчиков все пары, поэтому отдаём старый или 503
            if cached and time.time() - cached[0] < STALE_MAX_AGE:
                return cached[1]
            raise HTTPException(status_code=503, detail="Расписание временно недоступно")

        cached = (time.time(), events)
        _cache[group] = cached
        _save_state(group, *cached)
        return events


def make_uid(group, item):
    # Один и тот же UID при каждом обновлении, чтобы календарь не пересоздавал события
    # Преподаватели в ключе различают подгруппы, у которых одна пара в одно время
    teachers = item.get("teachers")
    key = "|".join(
        [str(item.get(k) or "") for k in ("date", "startTime", "endTime", "discipline", "groupType", "numberPair")]
        + sorted(teachers if isinstance(teachers, dict) else [])
    )
    return f"{hashlib.sha1(f'{group}|{key}'.encode()).hexdigest()}@funkov.space"


def build_calendar(group, events, skip_pa, alarm_minutes):
    cal = Calendar()
    cal.add("prodid", f"-//Schedule Parser ({group})//")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", f"Расписание {group}")
    cal.add("x-wr-timezone", "Europe/Moscow")
    cal.add("refresh-interval", timedelta(hours=1), parameters={"VALUE": "DURATION"})
    cal.add("x-published-ttl", "PT1H")

    stamp = datetime.now(TZ)
    seen = set()

    for item in events:
        if skip_pa and is_pa(item):
            continue

        try:
            start_dt = datetime.strptime(f"{item['date']} {item['startTime']}", "%d.%m.%Y %H:%M").replace(tzinfo=TZ)
            end_dt = datetime.strptime(f"{item['date']} {item['endTime']}", "%d.%m.%Y %H:%M").replace(tzinfo=TZ)
        except (KeyError, TypeError, ValueError):
            log.warning("skip event without valid time: %r", item)
            continue

        uid = make_uid(group, item)
        if uid in seen:
            continue
        seen.add(uid)

        discipline = item.get("discipline") or "Без названия"
        group_type = item.get("groupType")

        event = Event()
        event.add("uid", uid)
        event.add("dtstamp", stamp)
        event.add("summary", f"{discipline} ({group_type})" if group_type else discipline)
        event.add("dtstart", start_dt)
        event.add("dtend", end_dt)

        teachers_data = item.get("teachers")
        teacher_names = [
            info.get("fio")
            for info in (teachers_data.values() if isinstance(teachers_data, dict) else [])
            if isinstance(info, dict) and info.get("fio")
        ]
        description = ", ".join(teacher_names) if teacher_names else "Преподаватель не указан"
        if item.get("comment"):
            description += f"\nКомментарий: {item['comment']}"

        location_info = format_location(item)
        online_url = item.get("urlOnline")
        if online_url:
            event.add("url", online_url)
            location_info = f"URL / {location_info}"

        event.add("description", description)
        event.add("location", vText(location_info))
        if alarm_minutes:
            alarm = Alarm()
            alarm.add("uid", f"alarm-{uid}")
            alarm.add("action", "DISPLAY")
            alarm.add("description", event["summary"])
            alarm.add("trigger", timedelta(minutes=-alarm_minutes))
            event.add_component(alarm)

        cal.add_component(event)

    cal.add_missing_timezones()
    return cal.to_ical()


@app.api_route("/schedule.ics", methods=["GET", "HEAD"])
def get_schedule(
    group: str = Query(DEFAULT_GROUP, max_length=20),
    skip_pa: bool = Query(True),
    alarm: int = Query(ALARM_MINUTES, ge=0, le=1440),
):
    group = group.strip().upper().translate(LATIN_TO_CYRILLIC)
    if not GROUP_RE.match(group):
        raise HTTPException(status_code=400, detail="Неверное название группы")

    events = get_events(group)
    return Response(
        content=build_calendar(group, events, skip_pa, alarm),
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.get("/health")
def health():
    return {"ok": True}
