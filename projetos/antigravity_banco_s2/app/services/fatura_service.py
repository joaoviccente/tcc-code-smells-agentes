from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.fatura import Fatura
from app.models.cartao import Cartao
from app.schemas.fatura import FaturaCreate, FaturaPagamentoCreate, ProcessarAtrasosResponse
from app.config import (
    EstadoFatura,
    EstadoCartao,
    REGRAS_CATEGORIAS,
    DIAS_BLOQUEIO_CARTAO_FATURA,
    get_current_time,
)


def atualizar_estado_e_juros_fatura(fatura: Fatura, data_ref: Optional[date] = None) -> bool:
    """
    Aplica Regra 5:
    Fatura nao paga ate o vencimento passa ao estado atrasada e acumula juros conforme a categoria.
    Apos 10 dias de atraso, o cartao e bloqueado.
    Retorna True se o cartão foi bloqueado nesta atualização.
    """
    if fatura.estado == EstadoFatura.PAGA:
        return False

    if data_ref is None:
        data_ref = date.today()

    cartao_bloqueado = False

    if data_ref > fatura.data_vencimento:
        dias = (data_ref - fatura.data_vencimento).days
        fatura.estado = EstadoFatura.ATRASADA
        fatura.dias_atraso = dias

        cliente = fatura.cartao.conta.cliente
        regras = REGRAS_CATEGORIAS[cliente.categoria]

        # Juros proporcionais aos dias de atraso baseado na taxa mensal (mês comercial de 30 dias)
        # Juros = valor_original * (taxa_mensal * dias / 30)
        fator = (regras.taxa_juros_atraso_mensal * Decimal(dias)) / Decimal("30")
        juros = (fatura.valor_original * fator).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        fatura.juros_acumulados = juros
        fatura.valor = fatura.valor_original + juros

        # Apos 10 dias de atraso, o cartao e bloqueado
        if dias > DIAS_BLOQUEIO_CARTAO_FATURA:
            if fatura.cartao.estado == EstadoCartao.ATIVO:
                fatura.cartao.estado = EstadoCartao.BLOQUEADO
                cartao_bloqueado = True

    return cartao_bloqueado


def criar_fatura(db: Session, fatura_in: FaturaCreate) -> Fatura:
    cartao = db.query(Cartao).filter(Cartao.id == fatura_in.cartao_id).first()
    if not cartao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cartão com ID {fatura_in.cartao_id} não encontrado."
        )

    if cartao.estado == EstadoCartao.CANCELADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível gerar fatura para um cartão cancelado."
        )

    db_fatura = Fatura(
        cartao_id=fatura_in.cartao_id,
        mes_referencia=fatura_in.mes_referencia,
        valor=fatura_in.valor,
        valor_original=fatura_in.valor,
        data_vencimento=fatura_in.data_vencimento,
        estado=EstadoFatura.ABERTA,
        dias_atraso=0,
        juros_acumulados=Decimal("0.00"),
    )
    db.add(db_fatura)
    db.commit()
    db.refresh(db_fatura)

    # Se a data de vencimento já for no passado, atualiza atraso
    atualizar_estado_e_juros_fatura(db_fatura)
    db.commit()
    db.refresh(db_fatura)

    return db_fatura


def listar_faturas_por_cartao(
    db: Session,
    cartao_id: int,
    estado: Optional[EstadoFatura] = None,
) -> List[Fatura]:
    cartao = db.query(Cartao).filter(Cartao.id == cartao_id).first()
    if not cartao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cartão com ID {cartao_id} não encontrado."
        )

    query = db.query(Fatura).filter(Fatura.cartao_id == cartao_id)
    if estado:
        query = query.filter(Fatura.estado == estado)

    faturas = query.order_by(Fatura.data_vencimento.desc()).all()

    # Atualiza juros e status de atraso de cada fatura aberta
    modificado = False
    for f in faturas:
        if f.estado in [EstadoFatura.ABERTA, EstadoFatura.ATRASADA]:
            atualizar_estado_e_juros_fatura(f)
            modificado = True

    if modificado:
        db.commit()

    return faturas


def obter_fatura_por_id(db: Session, fatura_id: int) -> Fatura:
    fatura = db.query(Fatura).filter(Fatura.id == fatura_id).first()
    if not fatura:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fatura com ID {fatura_id} não encontrada."
        )

    atualizar_estado_e_juros_fatura(fatura)
    db.commit()
    db.refresh(fatura)
    return fatura


def registrar_pagamento_fatura(
    db: Session,
    fatura_id: int,
    pagamento_in: FaturaPagamentoCreate,
) -> Fatura:
    fatura = obter_fatura_por_id(db, fatura_id)

    if fatura.estado == EstadoFatura.PAGA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta fatura já foi paga anteriormente."
        )

    valor_pago = pagamento_in.valor if pagamento_in.valor is not None else fatura.valor
    data_pag = pagamento_in.data_pagamento or get_current_time()

    # Atualiza estado caso o valor pago quite a fatura
    if valor_pago >= fatura.valor:
        fatura.estado = EstadoFatura.PAGA
        fatura.data_pagamento = data_pag
        fatura.valor = Decimal("0.00")
    else:
        # Abate parcial
        fatura.valor -= valor_pago

    db.commit()
    db.refresh(fatura)
    return fatura


def processar_atrasos(db: Session, data_ref: Optional[date] = None) -> ProcessarAtrasosResponse:
    """
    Varre todas as faturas abertas e atrasadas, calculando juros e bloqueando cartões com > 10 dias de atraso.
    """
    faturas = db.query(Fatura).filter(
        Fatura.estado.in_([EstadoFatura.ABERTA, EstadoFatura.ATRASADA])
    ).all()

    atualizadas = 0
    cartoes_bloqueados = 0

    for f in faturas:
        bloqueou = atualizar_estado_e_juros_fatura(f, data_ref)
        if bloqueou:
            cartoes_bloqueados += 1
        atualizadas += 1

    db.commit()

    return ProcessarAtrasosResponse(
        faturas_atualizadas=atualizadas,
        cartoes_bloqueados=cartoes_bloqueados,
        mensagem=f"Processamento concluído: {atualizadas} fatura(s) verificadas, {cartoes_bloqueados} cartão(ões) bloqueado(s).",
    )
