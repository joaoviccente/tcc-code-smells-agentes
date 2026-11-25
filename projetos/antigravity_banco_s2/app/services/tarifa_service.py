from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.tarifa import Tarifa
from app.models.conta import Conta
from app.schemas.tarifa import TarifaCreate, CobrancaMensalResponse
from app.config import (
    EstadoConta,
    EstadoTarifa,
    TipoTarifa,
    REGRAS_CATEGORIAS,
    get_current_time,
)


def listar_tarifas_por_conta(
    db: Session,
    conta_id: int,
    estado: Optional[EstadoTarifa] = None,
) -> List[Tarifa]:
    conta = db.query(Conta).filter(Conta.id == conta_id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta com ID {conta_id} não encontrada."
        )

    query = db.query(Tarifa).filter(Tarifa.conta_id == conta_id)
    if estado:
        query = query.filter(Tarifa.estado == estado)

    return query.order_by(Tarifa.data.desc()).all()


def criar_tarifa(db: Session, tarifa_in: TarifaCreate) -> Tarifa:
    conta = db.query(Conta).filter(Conta.id == tarifa_in.conta_id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta com ID {tarifa_in.conta_id} não encontrada."
        )

    db_tarifa = Tarifa(
        conta_id=tarifa_in.conta_id,
        tipo=tarifa_in.tipo,
        valor=tarifa_in.valor,
        estado=tarifa_in.estado,
        data=get_current_time(),
    )
    db.add(db_tarifa)

    if tarifa_in.estado == EstadoTarifa.COBRADA:
        conta.saldo -= tarifa_in.valor
        if conta.saldo < Decimal("0.00") and conta.data_saldo_negativo_desde is None:
            conta.data_saldo_negativo_desde = get_current_time()

    db.commit()
    db.refresh(db_tarifa)
    return db_tarifa


def processar_cobranca_mensal(db: Session) -> CobrancaMensalResponse:
    """
    Cobra a tarifa mensal conforme a categoria do cliente:
    Comum: R$ 30,00
    Premium: R$ 0,00 (sem tarifa mensal)
    Empresarial: R$ 120,00
    """
    contas_ativas = db.query(Conta).filter(Conta.estado == EstadoConta.ATIVA).all()

    contas_processadas = 0
    total_cobrado = Decimal("0.00")
    agora = get_current_time()

    for conta in contas_ativas:
        cliente = conta.cliente
        regras = REGRAS_CATEGORIAS[cliente.categoria]

        if regras.tarifa_mensal > Decimal("0.00"):
            tarifa = Tarifa(
                conta_id=conta.id,
                tipo=TipoTarifa.MANUTENCAO_MENSAL.value,
                valor=regras.tarifa_mensal,
                data=agora,
                estado=EstadoTarifa.COBRADA,
            )
            db.add(tarifa)

            conta.saldo -= regras.tarifa_mensal
            if conta.saldo < Decimal("0.00") and conta.data_saldo_negativo_desde is None:
                conta.data_saldo_negativo_desde = agora

            total_cobrado += regras.tarifa_mensal
            contas_processadas += 1

    db.commit()

    return CobrancaMensalResponse(
        contas_processadas=contas_processadas,
        total_cobrado=total_cobrado,
        mensagem=f"Cobrança mensal processada para {contas_processadas} contas. Total cobrado: R$ {total_cobrado:.2f}.",
    )
