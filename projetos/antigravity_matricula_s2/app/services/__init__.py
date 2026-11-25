"""Módulo de serviços de regras de negócio."""

from app.services.horario_service import (
    SlotHorario,
    parse_horario,
    verificar_conflito_horarios,
)
from app.services.matricula_service import (
    normalizar_datetime_utc,
    atualizar_estado_turma,
    processar_expiracoes_48h,
    obter_fila_espera_ordenada,
    processar_proximo_fila_espera,
    solicitar_matricula,
    confirmar_matricula,
    cancelar_matricula,
    trancar_matricula,
    encerrar_periodo_matricula_turma,
)
from app.services.relatorio_service import (
    relatorio_disciplinas_mais_procuradas,
    relatorio_taxa_reprovacao,
    relatorio_ocupacao_departamentos,
)

__all__ = [
    "SlotHorario",
    "parse_horario",
    "verificar_conflito_horarios",
    "normalizar_datetime_utc",
    "atualizar_estado_turma",
    "processar_expiracoes_48h",
    "obter_fila_espera_ordenada",
    "processar_proximo_fila_espera",
    "solicitar_matricula",
    "confirmar_matricula",
    "cancelar_matricula",
    "trancar_matricula",
    "encerrar_periodo_matricula_turma",
    "relatorio_disciplinas_mais_procuradas",
    "relatorio_taxa_reprovacao",
    "relatorio_ocupacao_departamentos",
]
