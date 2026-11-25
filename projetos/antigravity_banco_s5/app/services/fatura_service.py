from datetime import date
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
    DIAS_BLOQUEIO_CARTAO_FATURA_ATRASADA,
)
from app.services.conta_service import ajustar_rastreamento_saldo_negativo
from app.utils import utc_now


def atualizar_status_fatura(fatura: Fatura, db: Session, data_referencia: Optional[date] = None) -> Fatura:
    """
    Regra de Negócio 5:
    Fatura não paga até o vencimento passa ao estado atrasada e acumula juros conforme a categoria.
    Após 10 dias de atraso, o cartão é bloqueado.
    """
    if fatura.estado == EstadoFatura.PAGA:
        return fatura

    hoje = data_referencia or date.today()

    if hoje > fatura.data_vencimento:
        fatura.estado = EstadoFatura.ATRASADA
        dias_atraso = (hoje - fatura.data_vencimento).days
        cliente = fatura.cartao.conta.cliente
        taxa_mensal = REGRAS_CATEGORIA[cliente.categoria]["taxa_juros_mensal"]

        # Juros pro-rata diário com base na taxa mensal de 30 dias
        taxa_diaria = taxa_mensal / Decimal("30")
        juros = round(fatura.valor * taxa_diaria * Decimal(dias_atraso), 2)
        fatura.juros_acumulados = juros

        if dias_atraso > DIAS_BLOQUEIO_CARTAO_FATURA_ATRASADA:
            if fatura.cartao.estado == EstadoCartao.ATIVO:
                fatura.cartao.estado = EstadoCartao.BLOQUEADO
        db.commit()
    return fatura


def criar_fatura(db: Session, fatura_in: FaturaCreate) -> Fatura:
    cartao = db.query(Cartao).filter(Cartao.id == fatura_in.cartao_id).first()
    if not cartao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cartão #{fatura_in.cartao_id} não encontrado.",
        )
    if cartao.estado == EstadoCartao.CANCELADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível emitir fatura para cartão cancelado.",
        )

    db_fatura = Fatura(
        cartao_id=fatura_in.cartao_id,
        mes_referencia=fatura_in.mes_referencia,
        valor=fatura_in.valor,
        data_vencimento=fatura_in.data_vencimento,
        estado=EstadoFatura.ABERTA,
        juros_acumulados=Decimal("0.00"),
    )
    db.add(db_fatura)
    db.commit()
    db.refresh(db_fatura)
    return db_fatura


def obter_fatura_por_id(db: Session, fatura_id: int) -> Fatura:
    fatura = db.query(Fatura).filter(Fatura.id == fatura_id).first()
    if not fatura:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fatura #{fatura_id} não encontrada.",
        )
    atualizar_status_fatura(fatura, db)
    return fatura


def listar_faturas_por_cartao(db: Session, cartao_id: int) -> List[Fatura]:
    cartao = db.query(Cartao).filter(Cartao.id == cartao_id).first()
    if not cartao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cartão #{cartao_id} não encontrado.",
        )
    faturas = db.query(Fatura).filter(Fatura.cartao_id == cartao_id).all()
    for fatura in faturas:
        atualizar_status_fatura(fatura, db)
    return faturas


def registrar_pagamento_fatura(
    db: Session, fatura_id: int, pagamento_in: FaturaPagamentoRequest
) -> Fatura:
    fatura = obter_fatura_por_id(db, fatura_id)

    if fatura.estado == EstadoFatura.PAGA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta fatura já foi paga anteriormente.",
        )

    atualizar_status_fatura(fatura, db)
    valor_total_devido = fatura.valor + fatura.juros_acumulados
    valor_a_pagar = pagamento_in.valor_pago or valor_total_devido

    # Se uma conta foi informada para débito
    if pagamento_in.conta_origem_id:
        conta = db.query(Conta).filter(Conta.id == pagamento_in.conta_origem_id).first()
        if not conta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta de origem #{pagamento_in.conta_origem_id} não encontrada.",
            )
        if conta.estado != "ativa":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A conta para pagamento deve estar ativa.",
            )
        saldo_disponivel = conta.saldo + conta.limite_credito
        if saldo_disponivel < valor_a_pagar:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Saldo insuficiente na conta para pagamento. Disponível: R$ {saldo_disponivel:.2f}, Necessário: R$ {valor_a_pagar:.2f}.",
            )
        conta.saldo -= valor_a_pagar
        ajustar_rastreamento_saldo_negativo(conta)

    fatura.valor_pago = valor_a_pagar
    fatura.data_pagamento = utc_now()
    fatura.estado = EstadoFatura.PAGA

    # Se o cartão estava bloqueado devido a atraso nesta fatura, verificar se ainda existem outras faturas atrasadas > 10 dias
    cartao = fatura.cartao
    if cartao.estado == EstadoCartao.BLOQUEADO:
        faturas_criticas = (
            db.query(Fatura)
            .filter(
                Fatura.cartao_id == cartao.id,
                Fatura.estado == EstadoFatura.ATRASADA,
                Fatura.id != fatura.id,
            )
            .all()
        )
        tem_atraso_critico = any(
            (date.today() - f.data_vencimento).days > DIAS_BLOQUEIO_CARTAO_FATURA_ATRASADA
            for f in faturas_criticas
        )
        if not tem_atraso_critico and cartao.conta.cliente.situacao == "ativo":
            cartao.estado = EstadoCartao.ATIVO

    db.commit()
    db.refresh(fatura)
    return fatura


def fatura_to_response(fatura: Fatura) -> FaturaResponse:
    dias_atraso = 0
    if fatura.estado == EstadoFatura.ATRASADA and fatura.data_vencimento:
        dias_atraso = max(0, (date.today() - fatura.data_vencimento).days)

    return FaturaResponse(
        id=fatura.id,
        cartao_id=fatura.cartao_id,
        mes_referencia=fatura.mes_referencia,
        valor=fatura.valor,
        data_vencimento=fatura.data_vencimento,
        data_pagamento=fatura.data_pagamento,
        valor_pago=fatura.valor_pago,
        juros_acumulados=fatura.juros_acumulados,
        valor_total_atual=fatura.valor + fatura.juros_acumulados,
        dias_atraso=dias_atraso,
        estado=fatura.estado,
    )
