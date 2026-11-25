"""Rotinas periodicas (regras 5 e 6, cobranca de tarifas pendentes).

Devem ser acionadas diariamente por um agendador (cron) via
POST /processamentos/diario. As regras tambem sao verificadas sob demanda
nas operacoes afetadas (saque, transferencia, consulta/pagamento de faturas).
"""
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import EstadoConta, EstadoTarifa
from app.models import Conta, Fatura, Tarifa
from app.servicos.comum import bloquear_cliente_e_cartoes, excede_prazo_negativo
from app.servicos.faturas import EM_ABERTO, atualizar_fatura
from app.servicos.tarifas import cobrar_pendentes_da_conta


def processar_diario(db: Session, hoje: date, agora: datetime) -> dict:
    res = {"data_referencia": hoje, "faturas_marcadas_atrasadas": 0,
           "faturas_com_juros_atualizados": 0, "cartoes_bloqueados_por_atraso": 0,
           "clientes_bloqueados_saldo_negativo": 0, "cartoes_bloqueados_saldo_negativo": 0,
           "tarifas_pendentes_cobradas": 0}

    # Regra 5: faturas vencidas -> atrasada, juros e bloqueio do cartao
    faturas = db.scalars(select(Fatura).where(
        Fatura.estado.in_(EM_ABERTO), Fatura.data_vencimento < hoje)).all()
    for f in faturas:
        r = atualizar_fatura(f, hoje)
        res["faturas_marcadas_atrasadas"] += r["atrasada"]
        res["faturas_com_juros_atualizados"] += r["juros"]
        res["cartoes_bloqueados_por_atraso"] += r["cartao_bloqueado"]

    # Cobranca de tarifas pendentes quando houver saldo
    contas_pend = db.scalars(select(Conta).where(
        Conta.estado != EstadoConta.ENCERRADA,
        Conta.id.in_(select(Tarifa.conta_id).where(Tarifa.estado == EstadoTarifa.PENDENTE)))).all()
    for c in contas_pend:
        res["tarifas_pendentes_cobradas"] += cobrar_pendentes_da_conta(db, c, agora)

    # Regra 6: saldo negativo por mais de 30 dias
    negativas = db.scalars(select(Conta).where(
        Conta.saldo < 0, Conta.negativo_desde.is_not(None),
        Conta.estado != EstadoConta.ENCERRADA)).all()
    vistos = set()
    for c in negativas:
        if c.cliente_id in vistos or not excede_prazo_negativo(c, hoje):
            continue
        vistos.add(c.cliente_id)
        bloqueado, n = bloquear_cliente_e_cartoes(db, c.cliente)
        res["clientes_bloqueados_saldo_negativo"] += bloqueado
        res["cartoes_bloqueados_saldo_negativo"] += n

    db.commit()
    return res
