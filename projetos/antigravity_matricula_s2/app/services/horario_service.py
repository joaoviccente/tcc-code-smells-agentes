"""Serviço de análise, interpretação e detecção de conflitos de horários de aulas."""

import re
from typing import List, Tuple, Optional
from datetime import time

# Mapeamento de identificadores de dias da semana
DIAS_MAP = {
    "SEG": 1, "SEGUNDA": 1, "SEG.": 1, "2": 1,
    "TER": 2, "TERCA": 2, "TERÇA": 2, "TER.": 2, "3": 2,
    "QUA": 3, "QUARTA": 3, "QUA.": 3, "4": 3,
    "QUI": 4, "QUINTA": 4, "QUI.": 4, "5": 4,
    "SEX": 5, "SEXTA": 5, "SEX.": 5, "6": 5,
    "SAB": 6, "SABADO": 6, "SÁBADO": 6, "SAB.": 6, "7": 6,
    "DOM": 7, "DOMINGO": 7, "DOM.": 7, "1": 7,
}

# Códigos de horários acadêmicos universitários
CODIGOS_HORARIO = {
    "M1": (time(7, 30), time(8, 20)),
    "M2": (time(8, 20), time(9, 10)),
    "M3": (time(9, 20), time(10, 10)),
    "M4": (time(10, 10), time(11, 0)),
    "M5": (time(11, 10), time(12, 0)),
    "M12": (time(7, 30), time(9, 10)),
    "M34": (time(9, 20), time(11, 0)),
    "M45": (time(10, 10), time(12, 0)),
    "T1": (time(13, 0), time(13, 50)),
    "T2": (time(13, 50), time(14, 40)),
    "T3": (time(14, 50), time(15, 40)),
    "T4": (time(15, 40), time(16, 30)),
    "T5": (time(16, 40), time(17, 30)),
    "T6": (time(17, 30), time(18, 20)),
    "T12": (time(13, 0), time(14, 40)),
    "T34": (time(14, 50), time(16, 30)),
    "T56": (time(16, 40), time(18, 20)),
    "N1": (time(18, 40), time(19, 30)),
    "N2": (time(19, 30), time(20, 20)),
    "N3": (time(20, 30), time(21, 20)),
    "N4": (time(21, 20), time(22, 10)),
    "N12": (time(18, 40), time(20, 20)),
    "N34": (time(20, 30), time(22, 10)),
}


class SlotHorario:
    """Representa um intervalo contínuo de horário em determinado dia da semana."""

    def __init__(self, dia: int, inicio: time, fim: time):
        self.dia = dia
        self.inicio = inicio
        self.fim = fim

    def conflita(self, outro: "SlotHorario") -> bool:
        """Verifica se há sobreposição temporal no mesmo dia da semana."""
        if self.dia != outro.dia:
            return False
        # Interseção de intervalos: inicio1 < fim2 e inicio2 < fim1
        return (self.inicio < outro.fim) and (outro.inicio < self.fim)

    def __repr__(self):
        return f"Slot(dia={self.dia}, {self.inicio.strftime('%H:%M')}-{self.fim.strftime('%H:%M')})"


def _parse_time(t_str: str) -> time:
    h, m = map(int, t_str.split(":"))
    return time(h, m)


def parse_horario(horario_str: str) -> List[SlotHorario]:
    """
    Analisa strings de horários nos mais variados formatos acadêmicos:
    - 'SEG 08:00-10:00, QUA 08:00-10:00'
    - 'TER-QUI 14:00-16:00'
    - '24M12'
    - 'SEG 08:00-10:00'
    """
    if not horario_str:
        return []

    slots: List[SlotHorario] = []
    texto = horario_str.strip().upper()

    # Divisão por separadores comuns
    partes = re.split(r"[,;/]+", texto)

    for parte in partes:
        parte = parte.strip()
        if not parte:
            continue

        # Códigos como '24M12' ou '35T34'
        match_codigo = re.match(r"^([2-7]+)([MTN]\d+)$", parte)
        if match_codigo:
            dias_str = match_codigo.group(1)
            codigo = match_codigo.group(2)
            if codigo in CODIGOS_HORARIO:
                t_ini, t_fim = CODIGOS_HORARIO[codigo]
                for d_char in dias_str:
                    dia_num = int(d_char) - 1
                    slots.append(SlotHorario(dia_num, t_ini, t_fim))
                continue

        # Intervalo de dias: 'TER-QUI 14:00-16:00'
        match_intervalo_dias = re.match(
            r"^([A-ZÇ]+)\s*-\s*([A-ZÇ]+)\s+(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})$",
            parte,
        )
        if match_intervalo_dias:
            d1_str, d2_str, h_ini_str, h_fim_str = match_intervalo_dias.groups()
            d1 = DIAS_MAP.get(d1_str)
            d2 = DIAS_MAP.get(d2_str)
            if d1 and d2:
                h_ini = _parse_time(h_ini_str)
                h_fim = _parse_time(h_fim_str)
                step = 1 if d1 <= d2 else -1
                for d in range(d1, d2 + step, step):
                    slots.append(SlotHorario(d, h_ini, h_fim))
                continue

        # Formato padrão: 'SEG 08:00-10:00' ou 'SEGUNDA 08:00 às 10:00'
        match_padrao = re.match(
            r"^([A-ZÇ0-9\s]+?)\s+(\d{1,2}:\d{2})\s*(?:-|ÀS|A)\s*(\d{1,2}:\d{2})$",
            parte,
        )
        if match_padrao:
            dias_raw, h_ini_str, h_fim_str = match_padrao.groups()
            h_ini = _parse_time(h_ini_str)
            h_fim = _parse_time(h_fim_str)

            dias_tokens = [t.strip() for t in dias_raw.strip().split() if t.strip() and t.strip() != "E"]
            for token in dias_tokens:
                if token in DIAS_MAP:
                    slots.append(SlotHorario(DIAS_MAP[token], h_ini, h_fim))
            continue

        # Formato genérico com horas encontradas
        horas_encontradas = re.findall(r"\b(\d{1,2}:\d{2})\b", parte)
        dias_encontrados = [DIAS_MAP[w] for w in parte.split() if w in DIAS_MAP]
        if len(horas_encontradas) >= 2 and dias_encontrados:
            h_ini = _parse_time(horas_encontradas[0])
            h_fim = _parse_time(horas_encontradas[1])
            for d in dias_encontrados:
                slots.append(SlotHorario(d, h_ini, h_fim))

    return slots


def verificar_conflito_horarios(horario1: str, horario2: str) -> bool:
    """
    Retorna True se houver sobreposição de horários entre duas turmas.
    """
    if not horario1 or not horario2:
        return False

    h1_limpo = re.sub(r"\s+", " ", horario1.strip().upper())
    h2_limpo = re.sub(r"\s+", " ", horario2.strip().upper())

    # Se as descrições forem idênticas
    if h1_limpo == h2_limpo:
        return True

    slots1 = parse_horario(horario1)
    slots2 = parse_horario(horario2)

    if slots1 and slots2:
        for s1 in slots1:
            for s2 in slots2:
                if s1.conflita(s2):
                    return True
        return False

    # Fallback para comparação textual de tokens
    tokens1 = set(h1_limpo.split())
    tokens2 = set(h2_limpo.split())
    intersecao = tokens1.intersection(tokens2)
    if any(len(t) > 3 for t in intersecao):
        return True

    return False
