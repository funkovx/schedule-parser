import uuid
import pytz
import re
import ast
from datetime import datetime
from icalendar import Calendar, Event, vText
from pyrinium import Pyrinium
from fastapi import FastAPI
from fastapi.responses import Response

app = FastAPI()

def format_location(item):
    classroom = item.get('classroom')
    place = item.get('place')
    
    raw_loc = classroom if classroom else place
    if not raw_loc:
        return "Место не указано"

    # 1. Убираем дублирование
    clean_loc = re.sub(r'(.{5,}?)\1', r'\1', raw_loc)

    # 2. Убираем технический мусор (-1К_20 -> К_20)
    clean_loc = re.sub(r'^[-\d\.\,\s]+', '', clean_loc).strip()

    # 3. Убираем префикс "К_", если дальше не цифра (К_Росатом -> Росатом)
    clean_loc = re.sub(r'^К_(?![0-9])', '', clean_loc).strip()

    return clean_loc

def parse_schedule(raw_data):
    if isinstance(raw_data, str):
        try:
            raw_data = ast.literal_eval(raw_data)
        except Exception:
            raw_data = {}
    return raw_data.get('events', [])

@app.get("/schedule.ics")
def get_schedule():
    c = Pyrinium()
    c.get_initial_data()
    
    raw_current = c.get_schedule("К0609-24")
    events_current = parse_schedule(raw_current)
    
    c.change_week(1)
    raw_next = c.get_schedule("К0609-24")
    events_next = parse_schedule(raw_next)

    all_events = events_current + events_next
    
    cal = Calendar()
    cal.add('prodid', '-//Pyrinium Schedule Parser//')
    cal.add('version', '2.0')
    tz = pytz.timezone('Europe/Moscow')

    for item in all_events:
        discipline = item.get('discipline', 'Без названия')
        
        if any(mark in discipline for mark in ["ППА", "ПА.", "ПА,"]):
            continue
            
        event = Event()
        event.add('uid', f"{uuid.uuid4()}@pyrinium.local")
        event.add('dtstamp', datetime.now(tz))
        
        start_dt = tz.localize(datetime.strptime(f"{item['date']} {item['startTime']}", "%d.%m.%Y %H:%M"))
        end_dt = tz.localize(datetime.strptime(f"{item['date']} {item['endTime']}", "%d.%m.%Y %H:%M"))
        
        group_type = item.get('groupType')
        event.add('summary', f"{discipline} ({group_type})" if group_type else discipline)
        event.add('dtstart', start_dt)
        event.add('dtend', end_dt)
        
        teachers_data = item.get('teachers', {})
        teacher_names = [info.get('fio') for info in (teachers_data.values() if isinstance(teachers_data, dict) else []) if info.get('fio')]
        
        description = f"Преподаватель: {', '.join(teacher_names) if teacher_names else 'Не указан'}"
        
        # Обработка ссылки и локации
        online_url = item.get('urlOnline')
        location_info = format_location(item)

        if online_url:
            event.add('url', online_url) # Кнопка "Open" в iOS
            final_location = f"URL / {location_info}"
        else:
            final_location = location_info
            
        if item.get('comment'):
            description += f"\nКомментарий: {item.get('comment')}"
            
        event.add('description', description)
        event.add('location', vText(final_location))
        cal.add_component(event)

    return Response(content=cal.to_ical(), media_type="text/calendar")
