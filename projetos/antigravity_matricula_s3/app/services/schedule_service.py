import re
from typing import List, NamedTuple

class TimeSlot(NamedTuple):
    day: str
    start_minutes: int
    end_minutes: int

DAY_ALIASES = {
    "SEG": "SEG", "SEGUNDA": "SEG", "MON": "SEG", "2": "SEG",
    "TER": "TER", "TERCA": "TER", "TERÇA": "TER", "TUE": "TER", "3": "TER",
    "QUA": "QUA", "QUARTA": "QUA", "WED": "QUA", "4": "QUA",
    "QUI": "QUI", "QUINTA": "QUI", "THU": "QUI", "5": "QUI",
    "SEX": "SEX", "SEXTA": "SEX", "FRI": "SEX", "6": "SEX",
    "SAB": "SAB", "SABADO": "SAB", "SÁBADO": "SAB", "SAT": "SAB", "7": "SAB",
    "DOM": "DOM", "DOMINGO": "DOM", "SUN": "DOM", "1": "DOM",
}

def parse_schedule(schedule_str: str) -> List[TimeSlot]:
    """
    Parses a schedule string such as:
    'SEG 08:00-10:00, QUA 08:00-10:00' or 'TER 14:00-16:00'
    """
    if not schedule_str:
        return []

    slots: List[TimeSlot] = []
    # Split by comma or semicolon
    parts = re.split(r'[,;]+', schedule_str)
    pattern = re.compile(r'([A-Za-z0-9_áéíóúÁÉÍÓÚçÇ]+)\s+(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})')

    for part in parts:
        part = part.strip()
        if not part:
            continue
        match = pattern.search(part)
        if match:
            raw_day, h1, m1, h2, m2 = match.groups()
            day_key = raw_day.upper()
            day = DAY_ALIASES.get(day_key, day_key)
            start_m = int(h1) * 60 + int(m1)
            end_m = int(h2) * 60 + int(m2)
            slots.append(TimeSlot(day=day, start_minutes=start_m, end_minutes=end_m))
        else:
            # Fallback: if user provided just day or custom string
            slots.append(TimeSlot(day=part.upper(), start_minutes=0, end_minutes=1440))

    return slots

def tem_conflito_horario(horario_a: str, horario_b: str) -> bool:
    """
    Verifica se dois horários têm sobreposição (conflito).
    Regra 6: Matrícula em turma cujo horário conflita com outra turma já confirmada do aluno é negada.
    """
    if not horario_a or not horario_b:
        return False

    # Exact string match is always a conflict
    if horario_a.strip().upper() == horario_b.strip().upper():
        return True

    slots_a = parse_schedule(horario_a)
    slots_b = parse_schedule(horario_b)

    for sa in slots_a:
        for sb in slots_b:
            if sa.day == sb.day:
                # Overlap exists if max(start) < min(end)
                if max(sa.start_minutes, sb.start_minutes) < min(sa.end_minutes, sb.end_minutes):
                    return True

    return False
