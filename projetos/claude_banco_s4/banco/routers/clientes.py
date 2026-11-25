from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..enums import Categoria, SituacaoCliente
from ..schemas import ClienteCreate, ClienteOut, ClienteUpdate, ContaOut
from ..services import cadastros
from ..services.comum import obter_cliente

router = APIRouter(prefix="/clientes", tags=["Clientes"])


@router.post("", response_model=ClienteOut, status_code=status.HTTP_201_CREATED)
def criar(dados: ClienteCreate, db: Session = Depends(get_db)):
    return cadastros.criar_cliente(db, dados)


@router.get("", response_model=list[ClienteOut])
def listar(
    categoria: Categoria | None = None,
    situacao: SituacaoCliente | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return cadastros.listar_clientes(db, categoria, situacao, skip, limit)


@router.get("/{cliente_id}", response_model=ClienteOut)
def obter(cliente_id: int, db: Session = Depends(get_db)):
    return obter_cliente(db, cliente_id)


@router.patch("/{cliente_id}", response_model=ClienteOut)
def atualizar(cliente_id: int, dados: ClienteUpdate, db: Session = Depends(get_db)):
    """Atualiza nome, e-mail, categoria e/ou situacao. O CPF e imutavel."""
    return cadastros.atualizar_cliente(db, cliente_id, dados)


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(cliente_id: int, db: Session = Depends(get_db)):
    """Remove cliente sem contas vinculadas (409 caso possua contas)."""
    cadastros.remover_cliente(db, cliente_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{cliente_id}/contas", response_model=list[ContaOut])
def contas_do_cliente(cliente_id: int, db: Session = Depends(get_db)):
    return obter_cliente(db, cliente_id).contas
