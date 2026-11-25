from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import servicos as sv
from app.database import get_db
from app.errors import Conflito, NaoEncontrado, RegraViolada
from app.models import Disciplina, Historico, PreRequisito, Turma
from app.schemas import (DisciplinaAtualizar, DisciplinaCriar, DisciplinaSaida,
                         PreRequisitoCriar)

router = APIRouter(prefix="/disciplinas", tags=["Disciplinas"])


@router.post("", response_model=DisciplinaSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: DisciplinaCriar, db: Session = Depends(get_db)):
    if db.scalar(select(Disciplina.id).where(Disciplina.codigo == dados.codigo)):
        raise Conflito("CODIGO_JA_CADASTRADO", f"Disciplina '{dados.codigo}' ja cadastrada")
    d = Disciplina(**dados.model_dump())
    db.add(d)
    db.commit()
    return d


@router.get("", response_model=list[DisciplinaSaida])
def listar(departamento: Optional[str] = None, skip: int = Query(0, ge=0),
           limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    stmt = select(Disciplina).order_by(Disciplina.codigo)
    if departamento:
        stmt = stmt.where(Disciplina.departamento == departamento)
    return db.scalars(stmt.offset(skip).limit(limit)).all()


@router.get("/{disciplina_id}", response_model=DisciplinaSaida)
def obter(disciplina_id: int, db: Session = Depends(get_db)):
    return sv.obter(db, Disciplina, disciplina_id, "Disciplina")


@router.patch("/{disciplina_id}", response_model=DisciplinaSaida)
@router.put("/{disciplina_id}", response_model=DisciplinaSaida, include_in_schema=False)
def atualizar(disciplina_id: int, dados: DisciplinaAtualizar, db: Session = Depends(get_db)):
    d = sv.obter(db, Disciplina, disciplina_id, "Disciplina")
    for k, v in dados.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(d, k, v)
    db.commit()
    return d


@router.delete("/{disciplina_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(disciplina_id: int, db: Session = Depends(get_db)):
    d = sv.obter(db, Disciplina, disciplina_id, "Disciplina")
    if db.scalar(select(Turma.id).where(Turma.disciplina_id == d.id).limit(1)) or \
            db.scalar(select(Historico.id).where(Historico.disciplina_id == d.id).limit(1)):
        raise Conflito("DISCIPLINA_COM_VINCULOS",
                       "Disciplina possui turmas ou registros de historico")
    if db.scalar(select(PreRequisito.id).where(PreRequisito.requisito_id == d.id).limit(1)):
        raise Conflito("DISCIPLINA_E_PRE_REQUISITO",
                       "Disciplina e pre-requisito de outra disciplina")
    db.query(PreRequisito).filter(PreRequisito.disciplina_id == d.id).delete()
    db.delete(d)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------ pre-requisitos
def _alcanca(db: Session, origem: int, alvo: int) -> bool:
    """True se 'origem' depende (direta ou indiretamente) de 'alvo'."""
    pilha, vistos = [origem], set()
    while pilha:
        atual = pilha.pop()
        if atual == alvo:
            return True
        if atual in vistos:
            continue
        vistos.add(atual)
        pilha.extend(db.scalars(select(PreRequisito.requisito_id)
                                .where(PreRequisito.disciplina_id == atual)).all())
    return False


@router.get("/{disciplina_id}/pre-requisitos", response_model=list[DisciplinaSaida],
            tags=["Pre-requisitos"])
def listar_prereqs(disciplina_id: int, db: Session = Depends(get_db)):
    sv.obter(db, Disciplina, disciplina_id, "Disciplina")
    return [p.requisito for p in db.scalars(
        select(PreRequisito).where(PreRequisito.disciplina_id == disciplina_id)).all()]


@router.post("/{disciplina_id}/pre-requisitos", response_model=list[DisciplinaSaida],
             status_code=status.HTTP_201_CREATED, tags=["Pre-requisitos"])
def adicionar_prereq(disciplina_id: int, dados: PreRequisitoCriar,
                     db: Session = Depends(get_db)):
    sv.obter(db, Disciplina, disciplina_id, "Disciplina")
    sv.obter(db, Disciplina, dados.requisito_id, "Disciplina")
    if dados.requisito_id == disciplina_id:
        raise RegraViolada("PRE_REQUISITO_INVALIDO",
                           "Disciplina nao pode ser pre-requisito de si mesma")
    if db.scalar(select(PreRequisito.id).where(PreRequisito.disciplina_id == disciplina_id,
                                               PreRequisito.requisito_id == dados.requisito_id)):
        raise Conflito("PRE_REQUISITO_JA_EXISTE", "Pre-requisito ja cadastrado")
    if _alcanca(db, dados.requisito_id, disciplina_id):
        raise RegraViolada("PRE_REQUISITO_CICLICO",
                           "Pre-requisito criaria dependencia circular")
    db.add(PreRequisito(disciplina_id=disciplina_id, requisito_id=dados.requisito_id))
    db.commit()
    return listar_prereqs(disciplina_id, db)


@router.delete("/{disciplina_id}/pre-requisitos/{requisito_id}",
               status_code=status.HTTP_204_NO_CONTENT, tags=["Pre-requisitos"])
def remover_prereq(disciplina_id: int, requisito_id: int, db: Session = Depends(get_db)):
    p = db.scalar(select(PreRequisito).where(PreRequisito.disciplina_id == disciplina_id,
                                             PreRequisito.requisito_id == requisito_id))
    if p is None:
        raise NaoEncontrado("PreRequisito", f"{disciplina_id}->{requisito_id}")
    db.delete(p)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
