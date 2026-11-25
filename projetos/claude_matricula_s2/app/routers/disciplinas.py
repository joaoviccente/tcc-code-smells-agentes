from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.database import get_db
from app.errors import Conflito, NaoEncontrado, RegraNegocio
from app.models import Disciplina, Historico, PreRequisito, Turma
from app.schemas import (
    DisciplinaCreate, DisciplinaOut, DisciplinaUpdate, PreRequisitoCreate, PreRequisitoOut,
)

router = APIRouter(prefix="/disciplinas", tags=["Disciplinas"])


@router.post("", response_model=DisciplinaOut, status_code=status.HTTP_201_CREATED)
def criar(dados: DisciplinaCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Disciplina.id).where(Disciplina.codigo == dados.codigo)):
        raise Conflito(f"ja existe disciplina com codigo '{dados.codigo}'")
    d = Disciplina(**dados.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.get("", response_model=list[DisciplinaOut])
def listar(
    departamento: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = select(Disciplina).order_by(Disciplina.codigo)
    if departamento:
        q = q.where(Disciplina.departamento == departamento)
    return db.scalars(q.offset(skip).limit(limit)).all()


@router.get("/{disciplina_id}", response_model=DisciplinaOut)
def obter(disciplina_id: int, db: Session = Depends(get_db)):
    return services.obter(db, Disciplina, disciplina_id, "disciplina")


@router.patch("/{disciplina_id}", response_model=DisciplinaOut)
def atualizar(disciplina_id: int, dados: DisciplinaUpdate, db: Session = Depends(get_db)):
    d = services.obter(db, Disciplina, disciplina_id, "disciplina")
    for k, v in dados.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(d, k, v)
    db.commit()
    db.refresh(d)
    return d


@router.delete("/{disciplina_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(disciplina_id: int, db: Session = Depends(get_db)):
    d = services.obter(db, Disciplina, disciplina_id, "disciplina")
    if db.scalar(select(Turma.id).where(Turma.disciplina_id == disciplina_id)):
        raise Conflito("disciplina possui turmas e nao pode ser removida")
    if db.scalar(select(Historico.id).where(Historico.disciplina_id == disciplina_id)):
        raise Conflito("disciplina possui registros de historico e nao pode ser removida")
    if db.scalar(select(PreRequisito.id).where(PreRequisito.requisito_id == disciplina_id)):
        raise Conflito("disciplina e pre-requisito de outra disciplina e nao pode ser removida")
    for p in db.scalars(select(PreRequisito).where(PreRequisito.disciplina_id == disciplina_id)).all():
        db.delete(p)
    db.delete(d)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ pre-requisitos
def _alcanca(db: Session, origem: int, alvo: int) -> bool:
    """True se `origem` exige (direta ou indiretamente) `alvo`."""
    pilha, vistos = [origem], set()
    while pilha:
        atual = pilha.pop()
        if atual == alvo:
            return True
        if atual in vistos:
            continue
        vistos.add(atual)
        pilha.extend(db.scalars(select(PreRequisito.requisito_id).where(PreRequisito.disciplina_id == atual)).all())
    return False


@router.get("/{disciplina_id}/pre-requisitos", response_model=list[PreRequisitoOut], tags=["Pre-requisitos"])
def listar_pre_requisitos(disciplina_id: int, db: Session = Depends(get_db)):
    services.obter(db, Disciplina, disciplina_id, "disciplina")
    return db.scalars(select(PreRequisito).where(PreRequisito.disciplina_id == disciplina_id)).all()


@router.post("/{disciplina_id}/pre-requisitos", response_model=PreRequisitoOut,
             status_code=status.HTTP_201_CREATED, tags=["Pre-requisitos"])
def adicionar_pre_requisito(disciplina_id: int, dados: PreRequisitoCreate, db: Session = Depends(get_db)):
    services.obter(db, Disciplina, disciplina_id, "disciplina")
    services.obter(db, Disciplina, dados.requisito_id, "disciplina requisito")
    if dados.requisito_id == disciplina_id:
        raise RegraNegocio("disciplina nao pode ser pre-requisito de si mesma")
    if db.scalar(select(PreRequisito.id).where(
            PreRequisito.disciplina_id == disciplina_id, PreRequisito.requisito_id == dados.requisito_id)):
        raise Conflito("pre-requisito ja cadastrado")
    if _alcanca(db, dados.requisito_id, disciplina_id):
        raise RegraNegocio("pre-requisito criaria dependencia circular")
    p = PreRequisito(disciplina_id=disciplina_id, requisito_id=dados.requisito_id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{disciplina_id}/pre-requisitos/{requisito_id}", status_code=status.HTTP_204_NO_CONTENT,
               tags=["Pre-requisitos"])
def remover_pre_requisito(disciplina_id: int, requisito_id: int, db: Session = Depends(get_db)):
    p = db.scalar(select(PreRequisito).where(
        PreRequisito.disciplina_id == disciplina_id, PreRequisito.requisito_id == requisito_id))
    if p is None:
        services.obter(db, Disciplina, disciplina_id, "disciplina")
        raise NaoEncontrado("pre-requisito nao encontrado")
    db.delete(p)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
