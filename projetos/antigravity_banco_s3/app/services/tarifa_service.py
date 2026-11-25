from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.tarifa import Tarifa
from app.models.conta import Conta
from app.schemas.tarifa import TarifaCreate, TarifaCobrarMensalidadeRequest
from app.config import (
    TipoTarifa,
    EstadoTarifa,
    REGRAS_CATEGORIA,
)


class TarifaService:
    @staticmethod
    def list_by_conta(
        db: Session, conta_id: int, skip: int = 0, limit: int = 100
    ) -> List[Tarifa]:
        conta = db.query(Conta).filter(Conta.id == conta_id).first()
        if not conta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta com ID {conta_id} não encontrada.",
            )
        return (
            db.query(Tarifa)
            .filter(Tarifa.conta_id == conta_id)
            .order_by(Tarifa.data.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    @staticmethod
    def create(db: Session, req: TarifaCreate) -> Tarifa:
        conta = db.query(Conta).filter(Conta.id == req.conta_id).first()
        if not conta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta com ID {req.conta_id} não encontrada.",
            )

        tarifa = Tarifa(
            conta_id=req.conta_id,
            tipo=req.tipo,
            valor=req.valor,
            estado=req.estado,
            data=datetime.now(timezone.utc),
        )
        db.add(tarifa)
        db.commit()
        db.refresh(tarifa)
        return tarifa

    @staticmethod
    def cobrar_mensalidade(
        db: Session, conta_id: int, req: TarifaCobrarMensalidadeRequest
    ) -> Tarifa:
        conta = db.query(Conta).filter(Conta.id == conta_id).first()
        if not conta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta com ID {conta_id} não encontrada.",
            )

        cliente = conta.cliente
        regras = REGRAS_CATEGORIA[cliente.categoria]
        tarifa_mensal = regras["tarifa_mensal"]

        if tarifa_mensal == Decimal("0.00"):
            # Premium não tem tarifa mensal (isenta)
            tarifa = Tarifa(
                conta_id=conta.id,
                tipo=TipoTarifa.MENSALIDADE,
                valor=Decimal("0.00"),
                estado=EstadoTarifa.ISENTA,
                data=datetime.now(timezone.utc),
            )
            db.add(tarifa)
            db.commit()
            db.refresh(tarifa)
            return tarifa

        estado_tarifa = EstadoTarifa.PENDENTE
        if req.debitar_saldo:
            disponivel = conta.saldo + conta.limite_credito
            if disponivel >= tarifa_mensal:
                conta.saldo -= tarifa_mensal
                if conta.saldo < Decimal("0.00") and conta.saldo_negativo_desde is None:
                    conta.saldo_negativo_desde = datetime.now(timezone.utc)
                estado_tarifa = EstadoTarifa.COBRADA
            else:
                estado_tarifa = EstadoTarifa.PENDENTE
        else:
            estado_tarifa = EstadoTarifa.PENDENTE

        tarifa = Tarifa(
            conta_id=conta.id,
            tipo=TipoTarifa.MENSALIDADE,
            valor=tarifa_mensal,
            estado=estado_tarifa,
            data=datetime.now(timezone.utc),
        )
        db.add(tarifa)
        db.commit()
        db.refresh(tarifa)
        return tarifa
