from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..enums import CategoriaAluno, EstadoMatricula, SituacaoAluno, SituacaoHistorico
from ..errors import Conflito
from ..models import Aluno, Historico, Matricula, Turma
from ..schemas import (
    SEMESTRE_PATTERN,
    AlunoCreate,
    AlunoOut,
    AlunoUpdate,
    HistoricoAlunoOut,
    HistoricoOut,
    MatriculaOut,
)
from ..servicos import obter_ou_404, preencher_posicao

router = APIRouter(prefix="/alunos", tags=["Alunos"])


def _verificar_unicidade(db: Session, dados: dict, ignorar_id: int | None = None) -> None:
    for campo in ("matricula", "email"):
        if campo in dados:
            q = select(Aluno.id).where(getattr(Aluno, campo) == dados[campo])
            if ignorar_id is not None:
                q = q.where(Aluno.id != ignorar_id)
            if db.scalar(q) is not None:
                raise Conflito(f"{campo.upper()}_DUPLICADO", f"Ja existe aluno com este {campo}.")


@router.post("", response_model=AlunoOut, status_code=201)
def criar_aluno(dados: AlunoCreate, db: Session = Depends(get_db)):
    valores = dados.model_dump()
    _verificar_unicidade(db, valores)
    aluno = Aluno(**valores)
    db.add(aluno)
    db.commit()
    return aluno


@router.get("", response_model=list[AlunoOut])
def listar_alunos(
    categoria: CategoriaAluno | None = None,
    situacao: SituacaoAluno | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = select(Aluno).order_by(Aluno.id).offset(skip).limit(limit)
    if categoria:
        q = q.where(Aluno.categoria == categoria)
    if situacao:
        q = q.where(Aluno.situacao == situacao)
    return db.scalars(q).all()


@router.get("/{aluno_id}", response_model=AlunoOut)
def obter_aluno(aluno_id: int, db: Session = Depends(get_db)):
    return obter_ou_404(db, Aluno, aluno_id, "Aluno")


def _atualizar(db: Session, aluno_id: int, valores: dict) -> Aluno:
    aluno = obter_ou_404(db, Aluno, aluno_id, "Aluno")
    _verificar_unicidade(db, valores, ignorar_id=aluno_id)
    for campo, valor in valores.items():
        setattr(aluno, campo, valor)
    db.commit()
    return aluno


@router.put("/{aluno_id}", response_model=AlunoOut)
def substituir_aluno(aluno_id: int, dados: AlunoCreate, db: Session = Depends(get_db)):
    return _atualizar(db, aluno_id, dados.model_dump())


@router.patch("/{aluno_id}", response_model=AlunoOut)
def atualizar_aluno(aluno_id: int, dados: AlunoUpdate, db: Session = Depends(get_db)):
    return _atualizar(db, aluno_id, dados.model_dump(exclude_unset=True))


@router.delete("/{aluno_id}", status_code=204)
def remover_aluno(aluno_id: int, db: Session = Depends(get_db)):
    aluno = obter_ou_404(db, Aluno, aluno_id, "Aluno")
    if aluno.matriculas or aluno.historico:
        raise Conflito(
            "ALUNO_COM_VINCULOS",
            "Aluno possui matriculas ou historico e nao pode ser removido; altere sua situacao.",
        )
    db.delete(aluno)
    db.commit()
    return Response(status_code=204)


@router.get("/{aluno_id}/matriculas", response_model=list[MatriculaOut])
def listar_matriculas_do_aluno(
    aluno_id: int,
    semestre: str | None = Query(None, pattern=SEMESTRE_PATTERN),
    estado: EstadoMatricula | None = None,
    db: Session = Depends(get_db),
):
    obter_ou_404(db, Aluno, aluno_id, "Aluno")
    q = (
        select(Matricula)
        .join(Turma, Matricula.turma_id == Turma.id)
        .where(Matricula.aluno_id == aluno_id)
        .order_by(Turma.semestre, Matricula.data_solicitacao, Matricula.id)
    )
    if semestre:
        q = q.where(Turma.semestre == semestre)
    if estado:
        q = q.where(Matricula.estado == estado)
    return preencher_posicao(db, list(db.scalars(q).all()))


@router.get("/{aluno_id}/historico", response_model=HistoricoAlunoOut)
def historico_do_aluno(
    aluno_id: int,
    semestre: str | None = Query(None, pattern=SEMESTRE_PATTERN),
    db: Session = Depends(get_db),
):
    aluno = obter_ou_404(db, Aluno, aluno_id, "Aluno")
    q = select(Historico).where(Historico.aluno_id == aluno_id).order_by(Historico.semestre, Historico.id)
    if semestre:
        q = q.where(Historico.semestre == semestre)
    registros = db.scalars(q).all()
    resumo = {s.value: 0 for s in SituacaoHistorico}
    for r in registros:
        resumo[r.situacao.value] += 1
    return HistoricoAlunoOut(
        aluno_id=aluno.id,
        aluno_nome=aluno.nome,
        resumo=resumo,
        registros=[HistoricoOut.model_validate(r) for r in registros],
    )
