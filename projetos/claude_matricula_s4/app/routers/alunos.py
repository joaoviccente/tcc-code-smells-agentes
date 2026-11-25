from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import servicos as sv
from app.database import get_db
from app.errors import Conflito
from app.models import (Aluno, CategoriaAluno, EstadoMatricula, Historico,
                        Matricula, SituacaoAluno, Turma)
from app.schemas import (AlunoAtualizar, AlunoCriar, AlunoSaida, HistoricoSaida,
                         MatriculaSaida, Semestre)
from app.routers.comum import historico_saida, matricula_saida

router = APIRouter(prefix="/alunos", tags=["Alunos"])


def _unicidade(db: Session, matricula: Optional[str], email: Optional[str], ignorar: int = 0):
    if matricula and db.scalar(select(Aluno.id).where(Aluno.matricula == matricula,
                                                      Aluno.id != ignorar)):
        raise Conflito("MATRICULA_JA_CADASTRADA", f"Matricula '{matricula}' ja cadastrada")
    if email and db.scalar(select(Aluno.id).where(Aluno.email == email, Aluno.id != ignorar)):
        raise Conflito("EMAIL_JA_CADASTRADO", f"E-mail '{email}' ja cadastrado")


@router.post("", response_model=AlunoSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: AlunoCriar, db: Session = Depends(get_db)):
    dados.email = dados.email.lower()
    _unicidade(db, dados.matricula, dados.email)
    aluno = Aluno(**dados.model_dump())
    db.add(aluno)
    db.commit()
    return aluno


@router.get("", response_model=list[AlunoSaida])
def listar(categoria: Optional[CategoriaAluno] = None, situacao: Optional[SituacaoAluno] = None,
           skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
           db: Session = Depends(get_db)):
    stmt = select(Aluno).order_by(Aluno.id)
    if categoria:
        stmt = stmt.where(Aluno.categoria == categoria)
    if situacao:
        stmt = stmt.where(Aluno.situacao == situacao)
    return db.scalars(stmt.offset(skip).limit(limit)).all()


@router.get("/{aluno_id}", response_model=AlunoSaida)
def obter(aluno_id: int, db: Session = Depends(get_db)):
    return sv.obter(db, Aluno, aluno_id, "Aluno")


@router.patch("/{aluno_id}", response_model=AlunoSaida)
@router.put("/{aluno_id}", response_model=AlunoSaida, include_in_schema=False)
def atualizar(aluno_id: int, dados: AlunoAtualizar, db: Session = Depends(get_db)):
    aluno = sv.obter(db, Aluno, aluno_id, "Aluno")
    campos = dados.model_dump(exclude_unset=True)
    if "email" in campos and campos["email"]:
        campos["email"] = campos["email"].lower()
    _unicidade(db, None, campos.get("email"), ignorar=aluno.id)
    for k, v in campos.items():
        if v is None:
            continue
        setattr(aluno, k, v)
    db.commit()
    return aluno


@router.delete("/{aluno_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(aluno_id: int, db: Session = Depends(get_db)):
    aluno = sv.obter(db, Aluno, aluno_id, "Aluno")
    if db.scalar(select(Matricula.id).where(Matricula.aluno_id == aluno.id).limit(1)) or \
            db.scalar(select(Historico.id).where(Historico.aluno_id == aluno.id).limit(1)):
        raise Conflito("ALUNO_COM_VINCULOS",
                       "Aluno possui matriculas ou historico e nao pode ser removido")
    db.delete(aluno)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{aluno_id}/matriculas", response_model=list[MatriculaSaida], tags=["Matriculas"])
def matriculas_do_aluno(aluno_id: int, semestre: Optional[Semestre] = None,
                        estado: Optional[EstadoMatricula] = None,
                        db: Session = Depends(get_db)):
    sv.obter(db, Aluno, aluno_id, "Aluno")
    stmt = select(Matricula).join(Turma).where(Matricula.aluno_id == aluno_id)
    if semestre:
        stmt = stmt.where(Turma.semestre == semestre)
    if estado:
        stmt = stmt.where(Matricula.estado == estado)
    return [matricula_saida(db, m) for m in db.scalars(stmt.order_by(Matricula.data)).all()]


@router.get("/{aluno_id}/historico", response_model=list[HistoricoSaida], tags=["Historico"])
def historico_do_aluno(aluno_id: int, db: Session = Depends(get_db)):
    sv.obter(db, Aluno, aluno_id, "Aluno")
    regs = db.scalars(select(Historico).where(Historico.aluno_id == aluno_id)
                      .order_by(Historico.semestre, Historico.id)).all()
    return [historico_saida(h) for h in regs]
