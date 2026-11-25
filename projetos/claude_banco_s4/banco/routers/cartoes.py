from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..enums import EstadoCartao, EstadoFatura
from ..schemas import CartaoCreate, CartaoOut, CartaoUpdate, CompraCartao, FaturaOut
from ..services import cadastros, faturas
from ..services.comum import obter_cartao

router = APIRouter(prefix="/cartoes", tags=["Cartoes"])


@router.post("", response_model=CartaoOut, status_code=status.HTTP_201_CREATED)
def criar(dados: CartaoCreate, db: Session = Depends(get_db)):
    return cadastros.criar_cartao(db, dados)


@router.get("", response_model=list[CartaoOut])
def listar(
    conta_id: int | None = None,
    estado: EstadoCartao | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return cadastros.listar_cartoes(db, conta_id, estado, skip, limit)


@router.get("/{cartao_id}", response_model=CartaoOut)
def obter(cartao_id: int, db: Session = Depends(get_db)):
    return obter_cartao(db, cartao_id)


@router.patch("/{cartao_id}", response_model=CartaoOut)
def atualizar(cartao_id: int, dados: CartaoUpdate, db: Session = Depends(get_db)):
    """Altera limite e/ou estado (ativo/bloqueado)."""
    return cadastros.atualizar_cartao(db, cartao_id, dados)


@router.delete("/{cartao_id}", response_model=CartaoOut, summary="Cancelar cartao")
def cancelar(cartao_id: int, db: Session = Depends(get_db)):
    return cadastros.cancelar_cartao(db, cartao_id)


@router.post("/{cartao_id}/compras", response_model=FaturaOut, status_code=status.HTTP_201_CREATED,
             tags=["Faturas"])
def compra(cartao_id: int, dados: CompraCartao, db: Session = Depends(get_db)):
    """Lanca uma compra na fatura aberta do mes corrente (respeitando o limite do cartao)."""
    return faturas.registrar_compra(db, cartao_id, dados.valor)


@router.get("/{cartao_id}/faturas", response_model=list[FaturaOut], tags=["Faturas"])
def listar_faturas(cartao_id: int, estado: EstadoFatura | None = None, db: Session = Depends(get_db)):
    return cadastros.faturas_do_cartao(db, cartao_id, estado)
