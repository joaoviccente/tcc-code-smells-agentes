import re
from dataclasses import dataclass
from datetime import time
from typing import List


DAYS_MAP = {
    "SEG": 1,
    "TER": 2,
    "QUA": 3,
    "QUI": 4,
    "SEX": 5,
    "SAB": 6,
    "DOM": 7,
}

SLOT_PATTERN = re.compile(
    r"^(SEG|TER|QUA|QUI|SEX|SAB|DOM)\s+([0-1]?[0-9]|2[0-3]):([0-5][0-9])-([0-1]?[0-9]|2[0-3]):([0-5][0-9])$",
    re.IGNORECASE
)


@dataclass(frozen=True)
class TimeSlot:
    day: str          # ex: "SEG"
    day_num: int      # 1 a 7
    start: time       # ex: time(8, 0)
    end: time         # ex: time(10, 0)

    def overlaps_with(self, other: "TimeSlot") -> bool:
        if self.day_num != other.day_num:
            return False
        # Interseção de intervalos abertos/semi-abertos [start, end)
        return self.start < other.end and other.start < self.end


def parse_schedule(schedule_str: str) -> List[TimeSlot]:
    """
    Analisa uma string de horário como 'SEG 08:00-10:00, QUA 08:00-10:00'
    e retorna uma lista de TimeSlot.
    Lança ValueError se o formato for inválido.
    """
    if not schedule_str or not schedule_str.strip():
        raise ValueError("Horário não pode ser vazio.")

    raw_slots = [s.strip() for s in re.split(r"[,;]+", schedule_str) if s.strip()]
    if not raw_slots:
        raise ValueError("Nenhum intervalo de horário fornecido.")

    parsed_slots: List[TimeSlot] = []

    for slot_str in raw_slots:
        match = SLOT_PATTERN.match(slot_str)
        if not match:
            raise ValueError(
                f"Formato de horário inválido: '{slot_str}'. "
                f"Formato esperado: 'DIA HH:MM-HH:MM' (ex: 'SEG 08:00-10:00, QUA 08:00-10:00'). "
                f"Dias válidos: {', '.join(DAYS_MAP.keys())}."
            )

        day_str = match.group(1).upper()
        h1, m1, h2, m2 = int(match.group(2)), int(match.group(3)), int(match.group(4)), int(match.group(5))

        start_time = time(h1, m1)
        end_time = time(h2, m2)

        if start_time >= end_time:
            raise ValueError(
                f"No intervalo '{slot_str}', o horário inicial ({start_time.strftime('%H:%M')}) "
                f"deve ser anterior ao horário final ({end_time.strftime('%H:%M')})."
            )

        slot = TimeSlot(
            day=day_str,
            day_num=DAYS_MAP[day_str],
            start=start_time,
            end=end_time
        )

        # Checar sobreposição interna dentro da própria turma
        for existing in parsed_slots:
            if slot.overlaps_with(existing):
                raise ValueError(
                    f"Conflito interno de horário: slot '{slot_str}' se sobrepõe com "
                    f"'{existing.day} {existing.start.strftime('%H:%M')}-{existing.end.strftime('%H:%M')}'."
                )

        parsed_slots.append(slot)

    return parsed_slots


def has_schedule_conflict(schedule1: str, schedule2: str) -> bool:
    """
    Verifica se duas strings de horário entram em conflito.
    Retorna True se houver sobreposição em qualquer dia/horário.
    """
    slots1 = parse_schedule(schedule1)
    slots2 = parse_schedule(schedule2)

    for s1 in slots1:
        for s2 in slots2:
            if s1.overlaps_with(s2):
                return True
    return False
