from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.database import get_db
from app.enums import CategoriaAluno, EstadoMatricula, SituacaoAluno
from app.errors import ErroNegocio
from app.models import Aluno, Disciplina, Historico, Matricula, Turma
from app.schemas import AlunoCreate, AlunoOut, AlunoUpdate, HistoricoCreate, HistoricoOut, MatriculaOut

router = APIRouter(prefix="/alunos", tags=["alunos"])


def _unicidade(db: Session, matricula: str | None, email: str | None, ignorar_id: int | None = None):
    if matricula and db.scalar(select(Aluno).where(Aluno.matricula == matricula, Aluno.id != ignorar_id)):
        raise ErroNegocio(409, "matricula_ja_cadastrada", f"Ja existe aluno com matricula '{matricula}'")
    if email and db.scalar(select(Aluno).where(Aluno.email == email, Aluno.id != ignorar_id)):
        raise ErroNegocio(409, "email_ja_cadastrado", f"Ja existe aluno com e-mail '{email}'")


@router.post("", response_model=AlunoOut, status_code=status.HTTP_201_CREATED)
def criar(dados: AlunoCreate, db: Session = Depends(get_db)):
    email = str(dados.email).lower()
    _unicidade(db, dados.matricula, email)
    aluno = Aluno(**dados.model_dump(exclude={"email"}), email=email)
    db.add(aluno)
    db.commit()
    return aluno


@router.get("", response_model=list[AlunoOut])
def listar(categoria: CategoriaAluno | None = None, situacao: SituacaoAluno | None = None,
           offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    q = select(Aluno).order_by(Aluno.id)
    if categoria:
        q = q.where(Aluno.categoria == categoria)
    if situacao:
        q = q.where(Aluno.situacao == situacao)
    return db.scalars(q.offset(offset).limit(limit)).all()


@router.get("/{aluno_id}", response_model=AlunoOut)
def obter(aluno_id: int, db: Session = Depends(get_db)):
    return services.obter(db, Aluno, aluno_id, "aluno")


@router.patch("/{aluno_id}", response_model=AlunoOut)
@router.put("/{aluno_id}", response_model=AlunoOut, include_in_schema=False)
def atualizar(aluno_id: int, dados: AlunoUpdate, db: Session = Depends(get_db)):
    aluno = services.obter(db, Aluno, aluno_id, "aluno")
    valores = dados.model_dump(exclude_unset=True)
    if valores.get("email"):
        valores["email"] = str(valores["email"]).lower()
    for campo, valor in valores.items():
        if valor is None:
            raise ErroNegocio(422, "valor_nulo", f"Campo '{campo}' nao pode ser nulo")
    _unicidade(db, None, valores.get("email"), ignorar_id=aluno.id)
    for campo, valor in valores.items():
        setattr(aluno, campo, valor)
    db.commit()
    return aluno


@router.delete("/{aluno_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(aluno_id: int, db: Session = Depends(get_db)):
    aluno = services.obter(db, Aluno, aluno_id, "aluno")
    if aluno.matriculas or aluno.historico:
        raise ErroNegocio(409, "aluno_com_vinculos",
                          "Aluno possui matriculas ou historico; altere a situacao em vez de remover")
    db.delete(aluno)
    db.commit()
    return Response(status_code=204)


@router.get("/{aluno_id}/matriculas", response_model=list[MatriculaOut])
def matriculas_do_aluno(aluno_id: int, semestre: str | None = Query(None, pattern=r"^\d{4}\.[12]$"),
                        estado: EstadoMatricula | None = None, db: Session = Depends(get_db)):
    services.processar_prazos(db)
    db.commit()
    services.obter(db, Aluno, aluno_id, "aluno")
    q = select(Matricula).join(Turma).where(Matricula.aluno_id == aluno_id).order_by(Matricula.data, Matricula.id)
    if semestre:
        q = q.where(Turma.semestre == semestre)
    if estado:
        q = q.where(Matricula.estado == estado)
    return db.scalars(q).all()


@router.get("/{aluno_id}/historico", response_model=list[HistoricoOut])
def historico(aluno_id: int, db: Session = Depends(get_db)):
    services.obter(db, Aluno, aluno_id, "aluno")
    return db.scalars(
        select(Historico).where(Historico.aluno_id == aluno_id).order_by(Historico.semestre, Historico.id)
    ).all()


@router.post("/{aluno_id}/historico", response_model=HistoricoOut, status_code=status.HTTP_201_CREATED)
def lancar_historico(aluno_id: int, dados: HistoricoCreate, db: Session = Depends(get_db)):
    """Lanca resultado final (nota/situacao) de uma disciplina cursada."""
    services.obter(db, Aluno, aluno_id, "aluno")
    services.obter(db, Disciplina, dados.disciplina_id, "disciplina")
    h = Historico(aluno_id=aluno_id, **dados.model_dump())
    db.add(h)
    db.commit()
    return h
