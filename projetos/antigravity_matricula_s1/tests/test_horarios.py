import pytest
from app.services.horario_service import verificar_conflito_horarios, parse_horario


def test_horarios_identicos():
    assert verificar_conflito_horarios("SEG 08:00-10:00", "SEG 08:00-10:00") is True
    assert verificar_conflito_horarios("qua 14:00-16:00", "QUA 14:00-16:00") is True


def test_horarios_sobreposicao():
    # 08:00-10:00 e 09:00-11:00 na segunda -> sobreposição
    assert verificar_conflito_horarios("SEG 08:00-10:00", "SEG 09:00-11:00") is True
    # 08:00-10:00 e 10:00-12:00 -> limite consecutivo, não deve sobrepor
    assert verificar_conflito_horarios("SEG 08:00-10:00", "SEG 10:00-12:00") is False


def test_dias_diferentes():
    # Segunda vs Quarta no mesmo horário -> sem conflito
    assert verificar_conflito_horarios("SEG 08:00-10:00", "QUA 08:00-10:00") is False
    assert verificar_conflito_horarios("TER 14:00-16:00", "QUI 14:00-16:00") is False


def test_horarios_compostos():
    # Composto: SEG 08:00-10:00, QUA 08:00-10:00
    h1 = "SEG 08:00-10:00, QUA 08:00-10:00"
    # Conflita na quarta
    h2 = "QUA 09:00-11:00"
    assert verificar_conflito_horarios(h1, h2) is True

    # Não conflita na sexta
    h3 = "SEX 08:00-10:00"
    assert verificar_conflito_horarios(h1, h3) is False


def test_codigos_universitarios():
    # 24M12 (Segunda e Quarta, Manhã 1 e 2)
    assert verificar_conflito_horarios("24M12", "24M12") is True
    assert verificar_conflito_horarios("24M12", "35M12") is False  # Terça e Quinta
