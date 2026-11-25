from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.database import get_db
from app.models import Cartao, EstadoCartao, Fatura
from app.schemas import (
    CartaoAtualizar, CartaoCriar, CartaoSaida, FaturaCriar, FaturaSaida, PagamentoFatura,
)
from app.services import cartoes as service
from app.services import faturas as faturas_service
from app.services.comum import obter

router = APIRouter(prefix="/cartoes", tags=["Cartoes"])
router_faturas = APIRouter(prefix="/faturas", tags=["Faturas"])


@router.post("", response_model=CartaoSaida, status_code=status.HTTP_201_CREATED)
def criar_cartao(dados: CartaoCriar, db: Session = Depends(get_db)):
    return service.criar(db, dados)


@router.get("", response_model=list[CartaoSaida])
def listar_cartoes(
    conta_id: int | None = None,
    estado: EstadoCartao | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = select(Cartao)
    if conta_id is not None:
        q = q.where(Cartao.conta_id == conta_id)
    if estado:
        q = q.where(Cartao.estado == estado)
    return db.scalars(q.order_by(Cartao.id).offset(skip).limit(limit)).all()


@router.get("/{cartao_id}", response_model=CartaoSaida)
def obter_cartao(cartao_id: int, db: Session = Depends(get_db)):
    return obter(db, Cartao, cartao_id, "Cartao")


@router.patch("/{cartao_id}", response_model=CartaoSaida)
def atualizar_cartao(cartao_id: int, dados: CartaoAtualizar, db: Session = Depends(get_db)):
    return service.atualizar(db, obter(db, Cartao, cartao_id, "Cartao"), dados)


@router.delete("/{cartao_id}", response_model=CartaoSaida, summary="Cancelar cartao")
def cancelar_cartao(cartao_id: int, db: Session = Depends(get_db)):
    return service.cancelar(db, obter(db, Cartao, cartao_id, "Cartao"))


# ----------------------------------------------------------------- faturas
@router.get("/{cartao_id}/faturas", response_model=list[FaturaSaida], tags=["Faturas"])
def listar_faturas(cartao_id: int, db: Session = Depends(get_db)):
    cartao = obter(db, Cartao, cartao_id, "Cartao")
    return faturas_service.listar_por_cartao(db, cartao, clock.agora())


@router.post("/{cartao_id}/faturas", response_model=FaturaSaida,
             status_code=status.HTTP_201_CREATED, tags=["Faturas"])
def lancar_fatura(cartao_id: int, dados: FaturaCriar, db: Session = Depends(get_db)):
    """Lanca a fatura de um mes de referencia (consolidacao das compras do cartao)."""
    cartao = obter(db, Cartao, cartao_id, "Cartao")
    return faturas_service.criar(db, cartao, dados, clock.agora())


@router_faturas.get("/{fatura_id}", response_model=FaturaSaida)
def obter_fatura(fatura_id: int, db: Session = Depends(get_db)):
    fatura = obter(db, Fatura, fatura_id, "Fatura")
    faturas_service.atualizar_situacao(fatura, clock.agora())
    db.commit()
    return fatura


@router_faturas.post("/{fatura_id}/pagamento", response_model=FaturaSaida)
def pagar_fatura(fatura_id: int, dados: PagamentoFatura, db: Session = Depends(get_db)):
    """Registra o pagamento integral da fatura (valor + juros de atraso, se houver)."""
    fatura = obter(db, Fatura, fatura_id, "Fatura")
    return faturas_service.pagar(db, fatura, dados.valor, clock.agora())
