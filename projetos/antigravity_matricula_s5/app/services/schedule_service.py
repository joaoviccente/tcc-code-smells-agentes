import re
from typing import List, Tuple, Optional

DAY_MAPPING = {
    "SEG": "SEG", "MON": "SEG", "SEGUNDA": "SEG",
    "TER": "TER", "TUE": "TER", "TERCA": "TER",
    "QUA": "QUA", "WED": "QUA", "QUARTA": "QUA",
    "QUI": "QUI", "THU": "QUI", "QUINTA": "QUI",
    "SEX": "SEX", "FRI": "SEX", "SEXTA": "SEX",
    "SAB": "SAB", "SAT": "SAB", "SABADO": "SAB",
    "DOM": "DOM", "SUN": "DOM", "DOMINGO": "DOM",
}

class TimeSlot:
    def __init__(self, day: str, start_minutes: int, end_minutes: int, raw: str):
        self.day = day
        self.start_minutes = start_minutes
        self.end_minutes = end_minutes
        self.raw = raw

    def overlaps(self, other: "TimeSlot") -> bool:
        if self.day != other.day:
            return False
        # Overlap happens if start_a < end_b and start_b < end_a
        return self.start_minutes < other.end_minutes and other.start_minutes < self.end_minutes

    def __repr__(self):
        return f"<TimeSlot {self.day} {self.start_minutes // 60:02d}:{self.start_minutes % 60:02d}-{self.end_minutes // 60:02d}:{self.end_minutes % 60:02d}>"


def parse_schedule(horario_str: str) -> List[TimeSlot]:
    """
    Analisa uma string de horário e retorna uma lista de TimeSlot.
    Formato esperado: 'DIA HH:MM-HH:MM' separados por vírgula ou ponto e vírgula.
    Exemplos:
      - 'SEG 08:00-10:00, QUA 08:00-10:00'
      - 'TER 14:00-16:00'
    """
    if not horario_str or not horario_str.strip():
        return []

    # Regex para capturar DIA e HORARIOS
    slot_pattern = re.compile(
        r"([A-Za-zçãáéíóúÇÃÁÉÍÓÚ]+)\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})"
    )

    slots: List[TimeSlot] = []
    # Divide por vírgula ou ponto e vírgula
    parts = re.split(r"[,;]", horario_str.strip())
    for part in parts:
        clean_part = part.strip()
        if not clean_part:
            continue
        match = slot_pattern.match(clean_part)
        if not match:
            # Caso o formato não seja rígido, pode levantar erro ou ignorar se for formato textual especial
            raise ValueError(
                f"Formato de horário inválido: '{clean_part}'. Use o formato 'DIA HH:MM-HH:MM' (ex: 'SEG 08:00-10:00')."
            )

        day_raw, h_start, m_start, h_end, m_end = match.groups()
        day_normalized = DAY_MAPPING.get(day_raw.upper())
        if not day_normalized:
            raise ValueError(f"Dia da semana desconhecido: '{day_raw}'. Use SEG, TER, QUA, QUI, SEX, SAB ou DOM.")

        start_min = int(h_start) * 60 + int(m_start)
        end_min = int(h_end) * 60 + int(m_end)

        if start_min >= end_min:
            raise ValueError(f"Horário de início deve ser menor que o de término em '{clean_part}'.")

        slots.append(TimeSlot(day=day_normalized, start_minutes=start_min, end_minutes=end_min, raw=clean_part))

    return slots


def check_schedule_conflict(horario_a: str, horario_b: str) -> Optional[Tuple[str, str]]:
    """
    Retorna uma tupla com os horários em conflito se houver choque, ou None se compatíveis.
    """
    try:
        slots_a = parse_schedule(horario_a)
        slots_b = parse_schedule(horario_b)
    except ValueError:
        # Se algum não puder ser parsed, fallback simples
        return None

    for slot_a in slots_a:
        for slot_b in slots_b:
            if slot_a.overlaps(slot_b):
                return (slot_a.raw, slot_b.raw)

    return None
