import pytest
from app.services.schedule_service import parse_schedule, check_schedule_conflict

def test_parse_valid_schedules():
    slots = parse_schedule("SEG 08:00-10:00, QUA 08:00-10:00")
    assert len(slots) == 2
    assert slots[0].day == "SEG"
    assert slots[0].start_minutes == 8 * 60
    assert slots[0].end_minutes == 10 * 60

    assert slots[1].day == "QUA"
    assert slots[1].start_minutes == 8 * 60
    assert slots[1].end_minutes == 10 * 60


def test_parse_invalid_format():
    with pytest.raises(ValueError):
        parse_schedule("FORMATO_INVALIDO")

    with pytest.raises(ValueError):
        parse_schedule("SEG 10:00-08:00")  # início maior que término


def test_schedule_conflicts():
    # Mesma faixa horária no mesmo dia: conflito
    assert check_schedule_conflict("SEG 08:00-10:00", "SEG 08:00-10:00") is not None

    # Sobreposição parcial: conflito
    assert check_schedule_conflict("SEG 08:00-10:00", "SEG 09:00-11:00") is not None

    # Horários consecutivos no mesmo dia: sem conflito
    assert check_schedule_conflict("SEG 08:00-10:00", "SEG 10:00-12:00") is None

    # Dias diferentes: sem conflito
    assert check_schedule_conflict("SEG 08:00-10:00", "TER 08:00-10:00") is None

    # Múltiplos dias com um choque
    assert check_schedule_conflict(
        "SEG 08:00-10:00, QUA 14:00-16:00",
        "TER 08:00-10:00, QUA 15:00-17:00"
    ) is not None
