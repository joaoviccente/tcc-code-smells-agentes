from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import Paginacao, get_db
from ..enums import EstadoExemplar
from ..models import Emprestimo, Exemplar, Livro, Reserva
from ..schemas import ExemplarAtualizar, ExemplarCriar, ExemplarSaida
from ..servicos import ErroNegocio, alocar_exemplar, alterar_estado_exemplar, obter
from .. import relogio

router = APIRouter(prefix="/exemplares", tags=["exemplares"])


def _checar_tombo(db: Session, codigo: str | None, ignorar_id: int | None = None) -> None:
    if codigo is None:
        return
    q = select(Exemplar.id).where(Exemplar.codigo_tombo == codigo)
    if ignorar_id is not None:
        q = q.where(Exemplar.id != ignorar_id)
    if db.scalar(q) is not None:
        raise ErroNegocio("ja existe exemplar com este codigo de tombo")


@router.post("", response_model=ExemplarSaida, status_code=status.HTTP_201_CREATED)
def criar(payload: ExemplarCriar, db: Session = Depends(get_db)):
    obter(db, Livro, payload.livro_id, "livro")
    _checar_tombo(db, payload.codigo_tombo)
    exemplar = Exemplar(livro_id=payload.livro_id, codigo_tombo=payload.codigo_tombo, estado=payload.estado)
    db.add(exemplar)
    db.flush()
    if exemplar.estado == EstadoExemplar.disponivel:
        alocar_exemplar(db, exemplar, relogio.agora())  # novo exemplar atende a fila, se houver
    db.commit()
    return exemplar


@router.get("", response_model=list[ExemplarSaida])
def listar(livro_id: int | None = None, estado: EstadoExemplar | None = None,
           pag: Paginacao = Depends(), db: Session = Depends(get_db)):
    q = select(Exemplar).order_by(Exemplar.id)
    if livro_id is not None:
        q = q.where(Exemplar.livro_id == livro_id)
    if estado:
        q = q.where(Exemplar.estado == estado)
    return list(db.scalars(pag.aplicar(q)))


@router.get("/{exemplar_id}", response_model=ExemplarSaida)
def detalhar(exemplar_id: int, db: Session = Depends(get_db)):
    return obter(db, Exemplar, exemplar_id, "exemplar")


@router.patch("/{exemplar_id}", response_model=ExemplarSaida)
def atualizar(exemplar_id: int, payload: ExemplarAtualizar, db: Session = Depends(get_db)):
    exemplar = obter(db, Exemplar, exemplar_id, "exemplar")
    dados = payload.model_dump(exclude_unset=True)
    nulos = [k for k, v in dados.items() if v is None]
    if nulos:
        raise ErroNegocio(f"campos nao podem ser nulos: {', '.join(nulos)}", 422)
    if "codigo_tombo" in dados:
        _checar_tombo(db, dados["codigo_tombo"], ignorar_id=exemplar_id)
        exemplar.codigo_tombo = dados["codigo_tombo"]
    if "estado" in dados:
        alterar_estado_exemplar(db, exemplar, dados["estado"])
    db.commit()
    return exemplar


@router.put("/{exemplar_id}", response_model=ExemplarSaida)
def substituir(exemplar_id: int, payload: ExemplarAtualizar, db: Session = Depends(get_db)):
    return atualizar(exemplar_id, payload, db)


@router.delete("/{exemplar_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(exemplar_id: int, db: Session = Depends(get_db)):
    exemplar = obter(db, Exemplar, exemplar_id, "exemplar")
    if db.scalar(select(func.count(Emprestimo.id)).where(Emprestimo.exemplar_id == exemplar_id)) or \
       db.scalar(select(func.count(Reserva.id)).where(Reserva.exemplar_id == exemplar_id)):
        raise ErroNegocio("exemplar possui historico de circulacao e nao pode ser removido; use o estado 'baixado'")
    db.delete(exemplar)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
