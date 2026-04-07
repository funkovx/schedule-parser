import uuid
import pytz
from datetime import datetime
from icalendar import Calendar, Event, vText
from pyrinium import Pyrinium
from fastapi import FastAPI
from fastapi.responses import Response

app = FastAPI()

def parse_schedule(raw_data):
    if isinstance(raw_data, str):
        import ast
        try:
            raw_data = ast.literal_eval(raw_data)
        except Exception:
            return []
    return raw_data.get('events', []) if isinstance(raw_data, dict) else []

@app.get("/schedule.ics")
def get_schedule():
    c = Pyrinium()
    c.get_initial_data()
    
    #Получаем текущую неделю
    raw_current = c.get_schedule("К0609-24")
    events_current = parse_schedule(raw_current)
    
    #Сдвигаем на следующую неделю и получаем данные
    c.change_week(1)
    raw_next = c.get_schedule("К0609-24")
    events_next = parse_schedule(raw_next)
    
    #Объединяем списки пар
    all_events = events_current + events_next
    
    #Формируем календарь
    cal = Calendar()
    cal.add('prodid', '-//Pyrinium Schedule Parser//')
    cal.add('version', '2.0')
    tz = pytz.timezone('Europe/Moscow')

    valid_events_count = 0

    for item in all_events:
        discipline = item.get('discipline', 'Без названия')
        
        #Фильтр ПА и ППА
        if "ППА" in discipline or "ПА." in discipline or "ПА," in discipline:
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
        
        location_parts = [p for p in [item.get('address'), f"Ауд. {item.get('classroom')}" if item.get('classroom') else None, item.get('place')] if p]
        
        description = f"Преподаватель: {', '.join(teacher_names) if teacher_names else 'Не указан'}"
        if item.get('urlOnline'):
            description += f"\nСсылка на занятие: {item.get('urlOnline')}"
            
        event.add('description', description)
        event.add('location', vText(" / ".join(location_parts) if location_parts else "Место не указано"))
        cal.add_component(event)
        
        valid_events_count += 1

    #Защита от ошибки "No valid events" в Apple Calendar, если пар реально 0
    if valid_events_count == 0:
        dummy_event = Event()
        dummy_event.add('uid', f"{uuid.uuid4()}@pyrinium.local")
        dummy_event.add('dtstamp', datetime.now(tz))
        dummy_event.add('summary', 'Пар нет')
        dummy_event.add('dtstart', datetime.now(tz))
        dummy_event.add('dtend', datetime.now(tz))
        cal.add_component(dummy_event)

    return Response(content=cal.to_ical(), media_type="text/calendar")