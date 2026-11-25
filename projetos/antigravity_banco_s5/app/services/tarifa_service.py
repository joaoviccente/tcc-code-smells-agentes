from decimal import Decimal
from typing import List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.tarifa import Tarifa
from app.models.conta import Conta
from app.config import TipoTarifa, EstadoTarifa, REGRAS_CATEGORIA
from app.services.conta_service import ajustar_rastreamento_saldo_negativo


def listar_tarifas_por_conta(db: Session, conta_id: int) -> List[Tarifa]:
    conta = db.query(Conta).filter(Conta.id == conta_id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta #{conta_id} não encontrada.",
        )
    return db.query(Tarifa).filter(Tarifa.conta_id == conta_id).all()


def cobrar_tarifa_mensal(db: Session, conta_id: int) -> Tarifa:
    conta = db.query(Conta).filter(Conta.id == conta_id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta #{conta_id} não encontrada.",
        )

    regras = REGRAS_CATEGORIA[conta.cliente.categoria]
    valor_tarifa = regras["tarifa_mensal"]

    if valor_tarifa <= Decimal("0.00"):
        # Cliente isento de tarifa mensal (ex: Premium)
        tarifa = Tarifa(
            conta_id=conta.id,
            tipo=TipoTarifa.MENSALIDADE,
            valor=Decimal("0.00"),
            estado=EstadoTarifa.ISENTA,
        )
        db.add(tarifa)
        db.commit()
        db.refresh(tarifa)
        return tarifa

    # Verificar limite de crédito da conta
    saldo_disponivel = conta.saldo + conta.limite_credito
    if saldo_disponivel < valor_tarifa:
        # Se não tiver saldo disponível para debitar imediatamente, registra como pendente
        tarifa = Tarifa(
            conta_id=conta.id,
            tipo=TipoTarifa.MENSALIDADE,
            valor=valor_tarifa,
            estado=EstadoTarifa.PENDENTE,
        )
        db.add(tarifa)
        db.commit()
        db.refresh(tarifa)
        return tarifa

    # Debita da conta
    conta.saldo -= valor_tarifa
    ajustar_rastreamento_saldo_negativo(conta)

    tarifa = Tarifa(
        conta_id=conta.id,
        tipo=TipoTarifa.MENSALIDADE,
        valor=valor_tarifa,
        estado=EstadoTarifa.COBRADA,
    )
    db.add(tarifa)
    db.commit()
    db.refresh(tarifa)
    return tarifa
