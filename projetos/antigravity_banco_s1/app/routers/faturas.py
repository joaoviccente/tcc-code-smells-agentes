from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.fatura import EstadoFatura
from app.schemas.fatura import FaturaCreate, FaturaPagamento, FaturaResponse
from app.services.fatura_service import FaturaService

router = APIRouter(tags=["Faturas"])


@router.post(
    "/cartoes/{cartao_id}/faturas",
    response_model=FaturaResponse,
    status_code=status.HTTP_201_CREATED,
)
def criar_fatura(
    cartao_id: int, fatura_in: FaturaCreate, db: Session = Depends(get_db)
):
    """Cria uma fatura vinculada a um cartão de crédito."""
    fatura = FaturaService.criar_fatura(db, cartao_id, fatura_in)
    return {
        "id": fatura.id,
        "cartao_id": fatura.cartao_id,
        "mes_referencia": fatura.mes_referencia,
        "valor": fatura.valor,
        "valor_pago": fatura.valor_pago,
        "juros_acumulados": fatura.juros_acumulados,
        "valor_total_devido": FaturaService.calcular_total_devido(fatura),
        "data_vencimento": fatura.data_vencimento,
        "data_pagamento": fatura.data_pagamento,
        "estado": fatura.estado,
        "data_criacao": fatura.data_criacao,
    }


@router.get(
    "/cartoes/{cartao_id}/faturas",
    response_model=List[FaturaResponse],
    status_code=status.HTTP_200_OK,
)
def listar_faturas_por_cartao(
    cartao_id: int,
    estado: Optional[EstadoFatura] = None,
    db: Session = Depends(get_db),
):
    """Lista as faturas emitidas para um determinado cartão."""
    faturas = FaturaService.listar_faturas_por_cartao(
        db, cartao_id, estado=estado.value if estado else None
    )
    return [
        {
            "id": f.id,
            "cartao_id": f.cartao_id,
            "mes_referencia": f.mes_referencia,
            "valor": f.valor,
            "valor_pago": f.valor_pago,
            "juros_acumulados": f.juros_acumulados,
            "valor_total_devido": FaturaService.calcular_total_devido(f),
            "data_vencimento": f.data_vencimento,
            "data_pagamento": f.data_pagamento,
            "estado": f.estado,
            "data_criacao": f.data_criacao,
        }
        for f in faturas
    ]


@router.get(
    "/faturas/{fatura_id}",
    response_model=FaturaResponse,
    status_code=status.HTTP_200_OK,
)
def obter_fatura(fatura_id: int, db: Session = Depends(get_db)):
    """Obtém os dados detalhados de uma fatura."""
    fatura = FaturaService.obter_fatura(db, fatura_id)
    return {
        "id": fatura.id,
        "cartao_id": fatura.cartao_id,
        "mes_referencia": fatura.mes_referencia,
        "valor": fatura.valor,
        "valor_pago": fatura.valor_pago,
        "juros_acumulados": fatura.juros_acumulados,
        "valor_total_devido": FaturaService.calcular_total_devido(fatura),
        "data_vencimento": fatura.data_vencimento,
        "data_pagamento": fatura.data_pagamento,
        "estado": fatura.estado,
        "data_criacao": fatura.data_criacao,
    }


@router.post(
    "/faturas/{fatura_id}/pagamento",
    response_model=FaturaResponse,
    status_code=status.HTTP_200_OK,
)
def registrar_pagamento_fatura(
    fatura_id: int,
    pagamento_in: FaturaPagamento,
    db: Session = Depends(get_db),
):
    """Registra o pagamento (total ou parcial) de uma fatura, opcionalmente debitando de uma conta."""
    fatura = FaturaService.registrar_pagamento(db, fatura_id, pagamento_in)
    return {
        "id": fatura.id,
        "cartao_id": fatura.cartao_id,
        "mes_referencia": fatura.mes_referencia,
        "valor": fatura.valor,
        "valor_pago": fatura.valor_pago,
        "juros_acumulados": fatura.juros_acumulados,
        "valor_total_devido": FaturaService.calcular_total_devido(fatura),
        "data_vencimento": fatura.data_vencimento,
        "data_pagamento": fatura.data_pagamento,
        "estado": fatura.estado,
        "data_criacao": fatura.data_criacao,
    }


@router.post("/faturas/verificar-atrasos", status_code=status.HTTP_200_OK)
def verificar_faturas_atrasadas(
    data_referencia: Optional[date] = None, db: Session = Depends(get_db)
):
    """
    Executa a verificação de faturas vencidas.
    Regra 5: Fatura não paga até o vencimento passa ao estado atrasada e acumula juros conforme a categoria.
    Após 10 dias de atraso, o cartão é bloqueado.
    """
    return FaturaService.atualizar_faturas_atrasadas(db, data_referencia=data_referencia)
