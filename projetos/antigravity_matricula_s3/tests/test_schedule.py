from app.services.schedule_service import parse_schedule, tem_conflito_horario

def test_parse_schedule():
    slots = parse_schedule("SEG 08:00-10:00, QUA 14:00-16:00")
    assert len(slots) == 2
    assert slots[0].day == "SEG"
    assert slots[0].start_minutes == 8 * 60
    assert slots[0].end_minutes == 10 * 60
    assert slots[1].day == "QUA"
    assert slots[1].start_minutes == 14 * 60
    assert slots[1].end_minutes == 16 * 60

def test_conflito_horario():
    # Mesmos horários -> conflito
    assert tem_conflito_horario("SEG 08:00-10:00", "SEG 08:00-10:00") is True

    # Dias diferentes -> sem conflito
    assert tem_conflito_horario("SEG 08:00-10:00", "TER 08:00-10:00") is False

    # Mesmo dia, horários adjacentes (sem sobreposição) -> sem conflito
    assert tem_conflito_horario("SEG 08:00-10:00", "SEG 10:00-12:00") is False

    # Mesmo dia, horários com sobreposição parcial
    assert tem_conflito_horario("SEG 08:00-10:00", "SEG 09:00-11:00") is True

    # Múltiplos horários com sobreposição em um dia
    assert tem_conflito_horario(
        "SEG 08:00-10:00, QUA 08:00-10:00",
        "TER 10:00-12:00, QUA 09:00-11:00"
    ) is True
