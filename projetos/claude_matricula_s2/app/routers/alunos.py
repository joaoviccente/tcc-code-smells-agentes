from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.database import get_db
from app.errors import Conflito
from app.models import (
    Aluno, Categoria, Disciplina, EstadoMatricula, Historico, Matricula, SituacaoAluno, Turma,
)
from app.schemas import (
    AlunoCreate, AlunoOut, AlunoUpdate, HistoricoCreate, HistoricoOut, MatriculaOut, Semestre,
)
from app.routers.matriculas import matricula_out

router = APIRouter(prefix="/alunos", tags=["Alunos"])


def _unicidade(db: Session, matricula: str | None, email: str | None, ignorar_id: int | None = None):
    if matricula and db.scalar(select(Aluno.id).where(Aluno.matricula == matricula, Aluno.id != (ignorar_id or 0))):
        raise Conflito(f"ja existe aluno com matricula '{matricula}'")
    if email and db.scalar(select(Aluno.id).where(Aluno.email == email, Aluno.id != (ignorar_id or 0))):
        raise Conflito(f"ja existe aluno com e-mail '{email}'")


@router.post("", response_model=AlunoOut, status_code=status.HTTP_201_CREATED)
def criar(dados: AlunoCreate, db: Session = Depends(get_db)):
    _unicidade(db, dados.matricula, dados.email)
    aluno = Aluno(**dados.model_dump())
    db.add(aluno)
    db.commit()
    db.refresh(aluno)
    return aluno


@router.get("", response_model=list[AlunoOut])
def listar(
    categoria: Categoria | None = None,
    situacao: SituacaoAluno | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = select(Aluno).order_by(Aluno.id)
    if categoria:
        q = q.where(Aluno.categoria == categoria)
    if situacao:
        q = q.where(Aluno.situacao == situacao)
    return db.scalars(q.offset(skip).limit(limit)).all()


@router.get("/{aluno_id}", response_model=AlunoOut)
def obter(aluno_id: int, db: Session = Depends(get_db)):
    return services.obter(db, Aluno, aluno_id, "aluno")


@router.patch("/{aluno_id}", response_model=AlunoOut)
def atualizar(aluno_id: int, dados: AlunoUpdate, db: Session = Depends(get_db)):
    aluno = services.obter(db, Aluno, aluno_id, "aluno")
    campos = dados.model_dump(exclude_unset=True, exclude_none=True)
    _unicidade(db, None, campos.get("email"), aluno_id)
    if "categoria" in campos and campos["categoria"] != aluno.categoria:
        ativas = db.scalar(select(Matricula.id).where(
            Matricula.aluno_id == aluno_id, Matricula.estado.in_(services.ATIVAS)))
        if ativas:
            raise Conflito("nao e possivel alterar a categoria de aluno com matriculas ativas")
    for k, v in campos.items():
        setattr(aluno, k, v)
    db.commit()
    db.refresh(aluno)
    return aluno


@router.delete("/{aluno_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(aluno_id: int, db: Session = Depends(get_db)):
    aluno = services.obter(db, Aluno, aluno_id, "aluno")
    if db.scalar(select(Matricula.id).where(Matricula.aluno_id == aluno_id)):
        raise Conflito("aluno possui matriculas registradas e nao pode ser removido")
    if db.scalar(select(Historico.id).where(Historico.aluno_id == aluno_id)):
        raise Conflito("aluno possui historico registrado e nao pode ser removido")
    db.delete(aluno)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ matriculas do aluno
@router.get("/{aluno_id}/matriculas", response_model=list[MatriculaOut], tags=["Matriculas"])
def matriculas_do_aluno(
    aluno_id: int,
    semestre: Semestre | None = None,
    estado: EstadoMatricula | None = None,
    db: Session = Depends(get_db),
):
    services.obter(db, Aluno, aluno_id, "aluno")
    q = (select(Matricula).join(Turma, Matricula.turma_id == Turma.id)
         .where(Matricula.aluno_id == aluno_id).order_by(Matricula.data, Matricula.id))
    if semestre:
        q = q.where(Turma.semestre == semestre)
    if estado:
        q = q.where(Matricula.estado == estado)
    return [matricula_out(db, m) for m in db.scalars(q).all()]


# ------------------------------------------------------------------ historico
def _historico_out(h: Historico) -> HistoricoOut:
    return HistoricoOut(
        id=h.id, aluno_id=h.aluno_id, disciplina_id=h.disciplina_id, disciplina_codigo=h.disciplina.codigo,
        disciplina_nome=h.disciplina.nome, semestre=h.semestre, nota=h.nota, situacao=h.situacao,
        observacao=h.observacao,
    )


@router.get("/{aluno_id}/historico", response_model=list[HistoricoOut], tags=["Historico"])
def historico(aluno_id: int, semestre: Semestre | None = None, db: Session = Depends(get_db)):
    services.obter(db, Aluno, aluno_id, "aluno")
    q = select(Historico).where(Historico.aluno_id == aluno_id).order_by(Historico.semestre, Historico.id)
    if semestre:
        q = q.where(Historico.semestre == semestre)
    return [_historico_out(h) for h in db.scalars(q).all()]


@router.post("/{aluno_id}/historico", response_model=HistoricoOut, status_code=status.HTTP_201_CREATED,
             tags=["Historico"])
def registrar_historico(aluno_id: int, dados: HistoricoCreate, db: Session = Depends(get_db)):
    """Lanca um resultado (aprovado/reprovado/trancado) no historico do aluno."""
    services.obter(db, Aluno, aluno_id, "aluno")
    services.obter(db, Disciplina, dados.disciplina_id, "disciplina")
    h = Historico(aluno_id=aluno_id, **dados.model_dump())
    db.add(h)
    db.commit()
    db.refresh(h)
    return _historico_out(h)
