"""Rotinas periodicas (regras temporais 5 e 6 e tarifa mensal)."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conta, EstadoCartao, EstadoFatura, Fatura, SituacaoCliente
from app.services import clientes as clientes_service
from app.services import faturas as faturas_service
from app.services import tarifas as tarifas_service
from app.services.comum import competencia_de, negativo_prolongado


def processamento_diario(db: Session, agora: datetime) -> dict[str, int]:
    r = {"faturas_fechadas": 0, "faturas_atrasadas": 0, "cartoes_bloqueados_atraso": 0,
         "clientes_bloqueados_saldo_negativo": 0, "cartoes_bloqueados_saldo_negativo": 0}

    # Regra 5
    for fatura in db.scalars(select(Fatura).where(Fatura.estado != EstadoFatura.PAGA)).all():
        estado_antes, cartao_antes = fatura.estado, fatura.cartao.estado
        faturas_service.atualizar_situacao(fatura, agora)
        if fatura.estado != estado_antes:
            if fatura.estado == EstadoFatura.FECHADA:
                r["faturas_fechadas"] += 1
            elif fatura.estado == EstadoFatura.ATRASADA:
                r["faturas_atrasadas"] += 1
        if cartao_antes == EstadoCartao.ATIVO and fatura.cartao.estado == EstadoCartao.BLOQUEADO:
            r["cartoes_bloqueados_atraso"] += 1

    # Regra 6
    contas = db.scalars(select(Conta).where(Conta.negativo_desde.is_not(None))).all()
    for conta in contas:
        if not negativo_prolongado(conta, agora):
            continue
        cliente = conta.cliente
        if cliente.situacao == SituacaoCliente.ATIVO:
            r["clientes_bloqueados_saldo_negativo"] += 1
        r["cartoes_bloqueados_saldo_negativo"] += clientes_service.bloquear_por_saldo_negativo(cliente)

    db.commit()
    return r


def tarifas_mensais(db: Session, competencia: str | None, agora: datetime) -> dict[str, int]:
    r = tarifas_service.gerar_tarifas_mensais(db, competencia or competencia_de(agora), agora)
    db.commit()
    return r
