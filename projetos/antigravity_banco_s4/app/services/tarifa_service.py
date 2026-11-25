from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.tarifa import Tarifa
from app.models.conta import Conta
from app.models.enums import EstadoConta, EstadoTarifa
from app.schemas.tarifa import CobrarMensalidadeResponse
from app.services.regras_categoria import RegrasCategoriaService


class TarifaService:
    @staticmethod
    def listar_por_conta(db: Session, conta_id: int) -> List[Tarifa]:
        conta = db.query(Conta).filter(Conta.id == conta_id).first()
        if not conta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta com ID {conta_id} não encontrada.",
            )
        return db.query(Tarifa).filter(Tarifa.conta_id == conta_id).order_by(Tarifa.data.desc()).all()

    @staticmethod
    def cobrar_mensalidades(db: Session, conta_id: Optional[int] = None) -> CobrarMensalidadeResponse:
        """
        Cobra a tarifa mensal das contas correntes com base na categoria do cliente:
        - Comum: R$ 30,00
        - Premium: sem tarifa mensal (R$ 0,00 - isenta)
        - Empresarial: R$ 120,00
        """
        query = db.query(Conta).filter(Conta.estado == EstadoConta.ATIVA)
        if conta_id:
            query = query.filter(Conta.id == conta_id)

        contas = query.all()
        contas_processadas = 0
        tarifas_cobradas = 0
        valor_total = Decimal("0.00")

        for conta in contas:
            contas_processadas += 1
            categoria = conta.cliente.categoria
            valor_tarifa = RegrasCategoriaService.get_tarifa_mensal(categoria)

            if valor_tarifa > Decimal("0.00"):
                # Debita o valor da conta corrente
                conta.saldo = Decimal(str(conta.saldo)) - valor_tarifa
                if conta.saldo < Decimal("0.00") and conta.data_saldo_negativo_inicio is None:
                    conta.data_saldo_negativo_inicio = datetime.utcnow()

                tarifa = Tarifa(
                    conta_id=conta.id,
                    tipo="mensalidade",
                    valor=valor_tarifa,
                    data=datetime.utcnow(),
                    estado=EstadoTarifa.COBRADA,
                )
                db.add(tarifa)
                tarifas_cobradas += 1
                valor_total += valor_tarifa
            else:
                # Categoria isenta (ex: Premium)
                tarifa = Tarifa(
                    conta_id=conta.id,
                    tipo="mensalidade",
                    valor=Decimal("0.00"),
                    data=datetime.utcnow(),
                    estado=EstadoTarifa.ISENTA,
                )
                db.add(tarifa)

        db.commit()

        return CobrarMensalidadeResponse(
            mensagem="Cobrança de tarifas mensais processada com sucesso.",
            contas_processadas=contas_processadas,
            tarifas_cobradas=tarifas_cobradas,
            valor_total_arrecadado=valor_total,
        )
