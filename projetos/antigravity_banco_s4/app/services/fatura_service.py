from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.fatura import Fatura
from app.models.cartao import Cartao
from app.models.enums import EstadoFatura, EstadoCartao
from app.schemas.fatura import FaturaCreate, FaturaPagamentoRequest, FaturaResponse
from app.services.regras_categoria import RegrasCategoriaService


class FaturaService:
    @classmethod
    def atualizar_fatura_e_cartao(cls, db: Session, fatura: Fatura, data_base: Optional[date] = None) -> None:
        """
        Regra 5: Fatura não paga até o vencimento passa ao estado atrasada
        e acumula juros conforme a categoria. Após 10 dias de atraso, o cartão é bloqueado.
        """
        hoje = data_base or date.today()
        
        # Se a fatura já está paga, não sofre mais juros nem atraso
        if fatura.estado == EstadoFatura.PAGA:
            return

        total_pago = Decimal(str(fatura.valor_pago))
        valor_base = Decimal(str(fatura.valor))

        if hoje > fatura.data_vencimento and total_pago < valor_base:
            dias_atraso = (hoje - fatura.data_vencimento).days
            fatura.estado = EstadoFatura.ATRASADA

            # Obter a categoria do cliente proprietário da conta do cartão
            categoria = fatura.cartao.conta.cliente.categoria

            # Calcular juros sobre o saldo devedor
            saldo_devedor = max(Decimal("0.00"), valor_base - total_pago)
            juros = RegrasCategoriaService.calcular_juros_fatura(
                valor=saldo_devedor,
                categoria=categoria,
                dias_atraso=dias_atraso,
            )
            fatura.juros_acumulados = juros

            # Após 10 dias de atraso, o cartão é bloqueado
            if dias_atraso > 10:
                if fatura.cartao.estado == EstadoCartao.ATIVO:
                    fatura.cartao.estado = EstadoCartao.BLOQUEADO

    @classmethod
    def criar_fatura(cls, db: Session, req: FaturaCreate) -> Fatura:
        cartao = db.query(Cartao).filter(Cartao.id == req.cartao_id).first()
        if not cartao:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cartão com ID {req.cartao_id} não encontrado.",
            )

        if cartao.estado == EstadoCartao.CANCELADO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível gerar fatura para um cartão cancelado.",
            )

        fatura = Fatura(
            cartao_id=req.cartao_id,
            mes_referencia=req.mes_referencia,
            valor=req.valor,
            valor_pago=Decimal("0.00"),
            data_vencimento=req.data_vencimento,
            estado=EstadoFatura.ABERTA,
            juros_acumulados=Decimal("0.00"),
        )
        db.add(fatura)
        db.commit()
        db.refresh(fatura)

        # Atualizar status inicial se a data de vencimento informada já estiver no passado
        cls.atualizar_fatura_e_cartao(db, fatura)
        db.commit()
        db.refresh(fatura)
        return fatura

    @classmethod
    def get_fatura(cls, db: Session, fatura_id: int) -> Fatura:
        fatura = db.query(Fatura).filter(Fatura.id == fatura_id).first()
        if not fatura:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Fatura com ID {fatura_id} não encontrada.",
            )
        cls.atualizar_fatura_e_cartao(db, fatura)
        db.commit()
        db.refresh(fatura)
        return fatura

    @classmethod
    def listar_por_cartao(cls, db: Session, cartao_id: int) -> List[Fatura]:
        cartao = db.query(Cartao).filter(Cartao.id == cartao_id).first()
        if not cartao:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cartão com ID {cartao_id} não encontrado.",
            )

        faturas = db.query(Fatura).filter(Fatura.cartao_id == cartao_id).all()
        for fatura in faturas:
            cls.atualizar_fatura_e_cartao(db, fatura)
        db.commit()

        return faturas

    @classmethod
    def registrar_pagamento(cls, db: Session, fatura_id: int, req: FaturaPagamentoRequest) -> Fatura:
        fatura = db.query(Fatura).filter(Fatura.id == fatura_id).first()
        if not fatura:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Fatura com ID {fatura_id} não encontrada.",
            )

        if fatura.estado == EstadoFatura.PAGA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta fatura já está integralmente paga.",
            )

        # Atualiza juros e estado caso esteja atrasada
        cls.atualizar_fatura_e_cartao(db, fatura)

        total_devido = (Decimal(str(fatura.valor)) + Decimal(str(fatura.juros_acumulados))) - Decimal(str(fatura.valor_pago))
        if req.valor > total_devido:
            # Permitir pagamento do total devido ou limitar ao devido
            fatura.valor_pago = Decimal(str(fatura.valor)) + Decimal(str(fatura.juros_acumulados))
        else:
            fatura.valor_pago = Decimal(str(fatura.valor_pago)) + Decimal(str(req.valor))

        # Checar se quitou a fatura
        if fatura.valor_pago >= (Decimal(str(fatura.valor)) + Decimal(str(fatura.juros_acumulados))):
            fatura.estado = EstadoFatura.PAGA
            fatura.data_pagamento = datetime.utcnow()

            # Se quitou e não existem outras faturas atrasadas no cartão, reabilitar se estiver apenas bloqueado por atraso
            outras_atrasadas = db.query(Fatura).filter(
                Fatura.cartao_id == fatura.cartao_id,
                Fatura.id != fatura.id,
                Fatura.estado == EstadoFatura.ATRASADA,
            ).count()
            if outras_atrasadas == 0 and fatura.cartao.estado == EstadoCartao.BLOQUEADO:
                # O cartão pode voltar a ativo se a conta e cliente estiverem ativos
                if fatura.cartao.conta.cliente.situacao.value == "ativo":
                    fatura.cartao.estado = EstadoCartao.ATIVO

        db.commit()
        db.refresh(fatura)
        return fatura

    @staticmethod
    def to_response(fatura: Fatura) -> FaturaResponse:
        total_com_juros = Decimal(str(fatura.valor)) + Decimal(str(fatura.juros_acumulados))
        devido = max(Decimal("0.00"), total_com_juros - Decimal(str(fatura.valor_pago)))
        return FaturaResponse(
            id=fatura.id,
            cartao_id=fatura.cartao_id,
            mes_referencia=fatura.mes_referencia,
            valor=fatura.valor,
            valor_pago=fatura.valor_pago,
            data_vencimento=fatura.data_vencimento,
            estado=fatura.estado,
            juros_acumulados=fatura.juros_acumulados,
            data_pagamento=fatura.data_pagamento,
            valor_total_devido=devido,
        )
