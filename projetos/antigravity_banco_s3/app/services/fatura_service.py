from datetime import datetime, date, timezone
from decimal import Decimal
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.fatura import Fatura
from app.models.cartao import Cartao
from app.models.conta import Conta
from app.schemas.fatura import FaturaCreate, FaturaPagamentoRequest, FaturaResponse
from app.config import (
    EstadoFatura,
    EstadoCartao,
    REGRAS_CATEGORIA,
)


class FaturaService:
    @staticmethod
    def atualizar_juros_e_atraso(db: Session, fatura: Fatura) -> Fatura:
        """
        Regra 5: Fatura não paga até o vencimento passa ao estado atrasada
        e acumula juros conforme a categoria. Após 10 dias de atraso, o cartão é bloqueado.
        """
        if fatura.estado in [EstadoFatura.ABERTA, EstadoFatura.ATRASADA]:
            hoje = date.today()
            if hoje > fatura.data_vencimento:
                fatura.estado = EstadoFatura.ATRASADA
                dias_atraso = (hoje - fatura.data_vencimento).days

                cartao = fatura.cartao
                cliente = cartao.conta.cliente
                taxa_mensal = REGRAS_CATEGORIA[cliente.categoria]["juros_atraso_mes"]

                # Cálculo de juros pro-rata diário com base na taxa mensal de 30 dias
                juros = (
                    fatura.valor * taxa_mensal * Decimal(dias_atraso) / Decimal("30")
                ).quantize(Decimal("0.01"))
                fatura.juros_acumulados = juros

                # Após 10 dias de atraso, o cartão é bloqueado
                if dias_atraso > 10 and cartao.estado == EstadoCartao.ATIVO:
                    cartao.estado = EstadoCartao.BLOQUEADO

                db.commit()
                db.refresh(fatura)
        return fatura

    @staticmethod
    def get_by_id(db: Session, fatura_id: int) -> Fatura:
        fatura = db.query(Fatura).filter(Fatura.id == fatura_id).first()
        if not fatura:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Fatura com ID {fatura_id} não encontrada.",
            )
        return FaturaService.atualizar_juros_e_atraso(db, fatura)

    @staticmethod
    def list_by_cartao(db: Session, cartao_id: int) -> List[Fatura]:
        cartao = db.query(Cartao).filter(Cartao.id == cartao_id).first()
        if not cartao:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cartão com ID {cartao_id} não encontrado.",
            )

        faturas = db.query(Fatura).filter(Fatura.cartao_id == cartao_id).all()
        for f in faturas:
            FaturaService.atualizar_juros_e_atraso(db, f)
        return faturas

    @staticmethod
    def create(db: Session, fatura_in: FaturaCreate) -> Fatura:
        cartao = db.query(Cartao).filter(Cartao.id == fatura_in.cartao_id).first()
        if not cartao:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cartão com ID {fatura_in.cartao_id} não encontrado.",
            )

        if cartao.estado == EstadoCartao.CANCELADO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível lançar fatura para cartão cancelado.",
            )

        fatura = Fatura(
            cartao_id=fatura_in.cartao_id,
            mes_referencia=fatura_in.mes_referencia,
            valor=fatura_in.valor,
            data_vencimento=fatura_in.data_vencimento,
            estado=EstadoFatura.ABERTA,
        )
        db.add(fatura)
        db.commit()
        db.refresh(fatura)

        # Atualiza atraso/juros caso a data de vencimento criada já tenha passado
        return FaturaService.atualizar_juros_e_atraso(db, fatura)

    @staticmethod
    def registrar_pagamento(
        db: Session, fatura_id: int, req: FaturaPagamentoRequest
    ) -> Fatura:
        fatura = FaturaService.get_by_id(db, fatura_id)

        if fatura.estado == EstadoFatura.PAGA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta fatura já está quitada.",
            )

        valor_total = fatura.valor + fatura.juros_acumulados
        valor_a_pagar = req.valor_pago or valor_total

        cartao = fatura.cartao
        conta = cartao.conta

        if req.debitar_da_conta:
            disponivel = conta.saldo + conta.limite_credito
            if valor_a_pagar > disponivel:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Saldo insuficiente na conta vinculada para pagar a fatura. "
                        f"Valor necessário: R$ {valor_a_pagar:.2f}, Disponível: R$ {disponivel:.2f}."
                    ),
                )
            conta.saldo -= valor_a_pagar
            if conta.saldo < Decimal("0.00") and conta.saldo_negativo_desde is None:
                conta.saldo_negativo_desde = datetime.now(timezone.utc)

        fatura.valor_pago = valor_a_pagar
        fatura.data_pagamento = datetime.now(timezone.utc)
        fatura.estado = EstadoFatura.PAGA

        # Se o cartão estava bloqueado por atraso nesta fatura, verifica se pode desbloquear
        if cartao.estado == EstadoCartao.BLOQUEADO:
            hoje = date.today()
            outras_faturas_atrasadas = (
                db.query(Fatura)
                .filter(
                    Fatura.cartao_id == cartao.id,
                    Fatura.id != fatura.id,
                    Fatura.estado.in_([EstadoFatura.ABERTA, EstadoFatura.ATRASADA]),
                    Fatura.data_vencimento < hoje,
                )
                .all()
            )
            # Verifica se há alguma com mais de 10 dias de atraso
            tem_mais_de_10_dias = any(
                (hoje - f.data_vencimento).days > 10 for f in outras_faturas_atrasadas
            )
            # Também verifica se a conta do cliente não está bloqueada pela regra 6
            cliente = conta.cliente
            if not tem_mais_de_10_dias and cliente.situacao == "ativo":
                cartao.estado = EstadoCartao.ATIVO

        db.commit()
        db.refresh(fatura)
        return fatura

    @staticmethod
    def processar_todas_faturas_atrasadas(db: Session) -> int:
        """Rotina para varrer faturas abertas e aplicar atraso/juros e bloqueio de cartão."""
        faturas = (
            db.query(Fatura)
            .filter(Fatura.estado.in_([EstadoFatura.ABERTA, EstadoFatura.ATRASADA]))
            .all()
        )
        modificadas = 0
        for f in faturas:
            FaturaService.atualizar_juros_e_atraso(db, f)
            modificadas += 1
        return modificadas
