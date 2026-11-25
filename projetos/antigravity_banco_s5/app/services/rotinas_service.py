from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.conta import Conta
from app.models.fatura import Fatura
from app.models.cartao import Cartao
from app.config import (
    EstadoConta,
    SituacaoCliente,
    EstadoCartao,
    EstadoFatura,
    DIAS_BLOQUEIO_CONTA_SALDO_NEGATIVO,
    DIAS_BLOQUEIO_CARTAO_FATURA_ATRASADA,
)
from app.services.fatura_service import atualizar_status_fatura
from app.utils import utc_now


def executar_verificacao_inadimplencia(
    db: Session,
    data_referencia: Optional[datetime] = None,
) -> Dict[str, Any]:
    agora = data_referencia or utc_now()
    hoje = agora.date() if isinstance(agora, datetime) else agora

    clientes_bloqueados = 0
    cartoes_bloqueados = 0
    faturas_atualizadas = 0

    # 1. Regra 6: Conta com saldo negativo por mais de 30 dias bloqueia o cliente e todos os seus cartões
    contas_negativas = (
        db.query(Conta)
        .filter(
            Conta.saldo < 0,
            Conta.data_saldo_negativo_inicio.isnot(None),
            Conta.estado != EstadoConta.ENCERRADA,
        )
        .all()
    )

    for conta in contas_negativas:
        dias_negativo = (agora - conta.data_saldo_negativo_inicio).days
        if dias_negativo > DIAS_BLOQUEIO_CONTA_SALDO_NEGATIVO:
            cliente = conta.cliente
            if cliente.situacao != SituacaoCliente.BLOQUEADO:
                cliente.situacao = SituacaoCliente.BLOQUEADO
                clientes_bloqueados += 1

            # Bloquear todos os cartões de todas as contas do cliente
            for c in cliente.contas:
                for cartao in c.cartoes:
                    if cartao.estado == EstadoCartao.ATIVO:
                        cartao.estado = EstadoCartao.BLOQUEADO
                        cartoes_bloqueados += 1

    # 2. Regra 5: Fatura não paga até o vencimento passa ao estado atrasada e acumula juros. Após 10 dias, bloqueia cartão.
    faturas_em_aberto = (
        db.query(Fatura)
        .filter(
            Fatura.estado.in_([EstadoFatura.ABERTA, EstadoFatura.ATRASADA]),
            Fatura.data_vencimento < hoje,
        )
        .all()
    )

    for fatura in faturas_em_aberto:
        cartao_estava_ativo = fatura.cartao.estado == EstadoCartao.ATIVO
        atualizar_status_fatura(fatura, db, data_referencia=hoje)
        faturas_atualizadas += 1
        if cartao_estava_ativo and fatura.cartao.estado == EstadoCartao.BLOQUEADO:
            cartoes_bloqueados += 1

    db.commit()

    return {
        "status": "sucesso",
        "data_verificacao": agora.isoformat(),
        "clientes_bloqueados_por_saldo_negativo": clientes_bloqueados,
        "cartoes_bloqueados": cartoes_bloqueados,
        "faturas_atualizadas": faturas_atualizadas,
    }
