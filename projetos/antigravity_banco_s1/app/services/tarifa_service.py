from decimal import Decimal
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import CATEGORY_RULES
from app.models.conta import Conta, EstadoConta
from app.models.tarifa import EstadoTarifa, Tarifa
from app.services.conta_service import ContaService


class TarifaService:
    @staticmethod
    def listar_tarifas_por_conta(
        db: Session, conta_id: int, estado: Optional[str] = None
    ) -> List[Tarifa]:
        conta = ContaService.obter_conta(db, conta_id)
        query = db.query(Tarifa).filter(Tarifa.conta_id == conta_id)
        if estado:
            query = query.filter(Tarifa.estado == estado)
        return query.order_by(Tarifa.data.desc()).all()

    @staticmethod
    def cobrar_tarifa_mensal(db: Session, conta_id: int) -> Tarifa:
        conta = ContaService.obter_conta(db, conta_id)
        if conta.estado == EstadoConta.ENCERRADA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível cobrar tarifa de conta encerrada.",
            )

        cliente = conta.cliente
        categoria_str = cliente.categoria.value if hasattr(cliente.categoria, "value") else str(cliente.categoria)
        regras = CATEGORY_RULES.get(categoria_str, CATEGORY_RULES["comum"])
        valor_tarifa = regras["tarifa_mensal"]

        if valor_tarifa == Decimal("0.00"):
            tarifa = Tarifa(
                conta_id=conta.id,
                tipo="mensalidade",
                valor=Decimal("0.00"),
                estado=EstadoTarifa.ISENTA,
                descricao=f"Isenção de tarifa mensal para categoria {categoria_str.capitalize()}",
            )
            db.add(tarifa)
            db.commit()
            db.refresh(tarifa)
            return tarifa

        # Verifica se a conta possui saldo/limite para debitar a tarifa
        saldo_disponivel = conta.saldo + conta.limite_credito
        if saldo_disponivel >= valor_tarifa:
            ContaService.ajustar_saldo_e_historico_negativo(conta, -valor_tarifa)
            tarifa = Tarifa(
                conta_id=conta.id,
                tipo="mensalidade",
                valor=valor_tarifa,
                estado=EstadoTarifa.COBRADA,
                descricao=f"Cobrança de tarifa mensal ({categoria_str.capitalize()})",
            )
        else:
            tarifa = Tarifa(
                conta_id=conta.id,
                tipo="mensalidade",
                valor=valor_tarifa,
                estado=EstadoTarifa.PENDENTE,
                descricao=f"Tarifa mensal pendente de saldo ({categoria_str.capitalize()})",
            )

        db.add(tarifa)
        db.commit()
        db.refresh(tarifa)
        return tarifa
