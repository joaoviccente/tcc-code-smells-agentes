from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from .. import errors, schemas
from ..database import get_db
from ..deps import db_sincronizado, paginacao
from ..models import (
    Aluno,
    CategoriaAluno,
    Disciplina,
    EstadoMatricula,
    Historico,
    Matricula,
    SituacaoAluno,
    Turma,
)
from ..services.matriculas import posicao_na_fila

router = APIRouter(prefix="/alunos", tags=["Alunos"])


def obter_aluno(db: Session, aluno_id: int) -> Aluno:
    aluno = db.get(Aluno, aluno_id)
    if aluno is None:
        raise errors.nao_encontrado("Aluno", aluno_id)
    return aluno


def _verificar_unicidade(db: Session, matricula: Optional[str], email: Optional[str], ignorar_id=None):
    conds = []
    if matricula is not None:
        conds.append(Aluno.matricula == matricula)
    if email is not None:
        conds.append(Aluno.email == email)
    if not conds:
        return
    q = select(Aluno).where(or_(*conds))
    if ignorar_id is not None:
        q = q.where(Aluno.id != ignorar_id)
    existente = db.scalars(q).first()
    if existente is not None:
        campo = "matricula" if existente.matricula == matricula else "email"
        raise errors.conflito("ALUNO_DUPLICADO", f"Já existe aluno com este {campo}.")


@router.post("", response_model=schemas.AlunoOut, status_code=status.HTTP_201_CREATED)
def criar_aluno(dados: schemas.AlunoCreate, db: Session = Depends(get_db)):
    dados.email = dados.email.lower()
    _verificar_unicidade(db, dados.matricula, dados.email)
    aluno = Aluno(**dados.model_dump())
    db.add(aluno)
    db.commit()
    return aluno


@router.get("", response_model=list[schemas.AlunoOut])
def listar_alunos(
    categoria: Optional[CategoriaAluno] = None,
    situacao: Optional[SituacaoAluno] = None,
    pag: tuple[int, int] = Depends(paginacao),
    db: Session = Depends(get_db),
):
    q = select(Aluno).order_by(Aluno.id)
    if categoria:
        q = q.where(Aluno.categoria == categoria)
    if situacao:
        q = q.where(Aluno.situacao == situacao)
    return db.scalars(q.offset(pag[0]).limit(pag[1])).all()


@router.get("/{aluno_id}", response_model=schemas.AlunoOut)
def obter(aluno_id: int, db: Session = Depends(get_db)):
    return obter_aluno(db, aluno_id)


@router.patch("/{aluno_id}", response_model=schemas.AlunoOut)
def atualizar_aluno(aluno_id: int, dados: schemas.AlunoUpdate, db: Session = Depends(get_db)):
    aluno = obter_aluno(db, aluno_id)
    valores = dados.model_dump(exclude_unset=True)
    if "email" in valores:
        valores["email"] = valores["email"].lower()
    _verificar_unicidade(db, valores.get("matricula"), valores.get("email"), ignorar_id=aluno.id)
    for k, v in valores.items():
        setattr(aluno, k, v)
    db.commit()
    return aluno


@router.delete("/{aluno_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_aluno(aluno_id: int, db: Session = Depends(get_db)):
    aluno = obter_aluno(db, aluno_id)
    em_uso = db.scalar(select(exists().where(Matricula.aluno_id == aluno.id))) or db.scalar(
        select(exists().where(Historico.aluno_id == aluno.id))
    )
    if em_uso:
        raise errors.conflito(
            "ALUNO_EM_USO", "Aluno possui matrículas ou histórico e não pode ser removido."
        )
    db.delete(aluno)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------- matrículas
@router.get("/{aluno_id}/matriculas", response_model=list[schemas.MatriculaOut])
def listar_matriculas_do_aluno(
    aluno_id: int,
    semestre: Optional[str] = Query(default=None, pattern=schemas.SEMESTRE_REGEX),
    estado: Optional[EstadoMatricula] = None,
    db: Session = Depends(db_sincronizado),
):
    obter_aluno(db, aluno_id)
    q = select(Matricula).join(Turma).where(Matricula.aluno_id == aluno_id)
    if semestre:
        q = q.where(Turma.semestre == semestre)
    if estado:
        q = q.where(Matricula.estado == estado)
    saida = []
    for m in db.scalars(q.order_by(Turma.semestre, Matricula.id)).all():
        out = schemas.MatriculaOut.model_validate(m)
        out.posicao_lista_espera = posicao_na_fila(db, m)
        saida.append(out)
    return saida


# -------------------------------------------------------------- histórico
@router.get("/{aluno_id}/historico", response_model=list[schemas.HistoricoOut])
def consultar_historico(
    aluno_id: int,
    semestre: Optional[str] = Query(default=None, pattern=schemas.SEMESTRE_REGEX),
    db: Session = Depends(get_db),
):
    obter_aluno(db, aluno_id)
    q = select(Historico).where(Historico.aluno_id == aluno_id)
    if semestre:
        q = q.where(Historico.semestre == semestre)
    return db.scalars(q.order_by(Historico.semestre, Historico.id)).all()


@router.post(
    "/{aluno_id}/historico",
    response_model=schemas.HistoricoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Lançar registro no histórico (ex.: nota final de disciplina)",
)
def lancar_historico(
    aluno_id: int, dados: schemas.HistoricoCreate, db: Session = Depends(get_db)
):
    obter_aluno(db, aluno_id)
    if db.get(Disciplina, dados.disciplina_id) is None:
        raise errors.nao_encontrado("Disciplina", dados.disciplina_id)
    registro = Historico(aluno_id=aluno_id, **dados.model_dump())
    db.add(registro)
    db.commit()
    return registro
