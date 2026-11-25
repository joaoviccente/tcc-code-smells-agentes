from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..errors import Conflito, NaoEncontrado, RegraViolada
from ..models import Disciplina, Historico, PreRequisito, Turma
from ..schemas import DisciplinaCreate, DisciplinaOut, DisciplinaUpdate, PreRequisitoCreate
from ..servicos import obter_ou_404

router = APIRouter(prefix="/disciplinas", tags=["Disciplinas"])


def _verificar_codigo(db: Session, codigo: str | None, ignorar_id: int | None = None) -> None:
    if codigo is None:
        return
    q = select(Disciplina.id).where(Disciplina.codigo == codigo)
    if ignorar_id is not None:
        q = q.where(Disciplina.id != ignorar_id)
    if db.scalar(q) is not None:
        raise Conflito("CODIGO_DUPLICADO", f"Ja existe disciplina com o codigo {codigo}.")


@router.post("", response_model=DisciplinaOut, status_code=201)
def criar_disciplina(dados: DisciplinaCreate, db: Session = Depends(get_db)):
    _verificar_codigo(db, dados.codigo)
    d = Disciplina(**dados.model_dump())
    db.add(d)
    db.commit()
    return d


@router.get("", response_model=list[DisciplinaOut])
def listar_disciplinas(
    departamento: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = select(Disciplina).order_by(Disciplina.codigo).offset(skip).limit(limit)
    if departamento:
        q = q.where(Disciplina.departamento == departamento)
    return db.scalars(q).all()


@router.get("/{disciplina_id}", response_model=DisciplinaOut)
def obter_disciplina(disciplina_id: int, db: Session = Depends(get_db)):
    return obter_ou_404(db, Disciplina, disciplina_id, "Disciplina")


def _atualizar(db: Session, disciplina_id: int, valores: dict) -> Disciplina:
    d = obter_ou_404(db, Disciplina, disciplina_id, "Disciplina")
    _verificar_codigo(db, valores.get("codigo"), ignorar_id=disciplina_id)
    for campo, valor in valores.items():
        setattr(d, campo, valor)
    db.commit()
    return d


@router.put("/{disciplina_id}", response_model=DisciplinaOut)
def substituir_disciplina(disciplina_id: int, dados: DisciplinaCreate, db: Session = Depends(get_db)):
    return _atualizar(db, disciplina_id, dados.model_dump())


@router.patch("/{disciplina_id}", response_model=DisciplinaOut)
def atualizar_disciplina(disciplina_id: int, dados: DisciplinaUpdate, db: Session = Depends(get_db)):
    return _atualizar(db, disciplina_id, dados.model_dump(exclude_unset=True))


@router.delete("/{disciplina_id}", status_code=204)
def remover_disciplina(disciplina_id: int, db: Session = Depends(get_db)):
    d = obter_ou_404(db, Disciplina, disciplina_id, "Disciplina")
    possui_turmas = db.scalar(select(Turma.id).where(Turma.disciplina_id == d.id).limit(1))
    possui_hist = db.scalar(select(Historico.id).where(Historico.disciplina_id == d.id).limit(1))
    e_requisito = db.scalar(select(PreRequisito.id).where(PreRequisito.requisito_id == d.id).limit(1))
    if possui_turmas or possui_hist or e_requisito:
        raise Conflito(
            "DISCIPLINA_COM_VINCULOS",
            "Disciplina possui turmas, historico ou e pre-requisito de outra disciplina.",
        )
    for pr in db.scalars(select(PreRequisito).where(PreRequisito.disciplina_id == d.id)).all():
        db.delete(pr)
    db.delete(d)
    db.commit()
    return Response(status_code=204)


# ------------------------------------------------------------ pre-requisitos
def _requisitos_transitivos(db: Session, disciplina_id: int) -> set[int]:
    visitados: set[int] = set()
    pilha = [disciplina_id]
    while pilha:
        atual = pilha.pop()
        for req in db.scalars(select(PreRequisito.requisito_id).where(PreRequisito.disciplina_id == atual)):
            if req not in visitados:
                visitados.add(req)
                pilha.append(req)
    return visitados


@router.get("/{disciplina_id}/pre-requisitos", response_model=list[DisciplinaOut])
def listar_pre_requisitos(disciplina_id: int, db: Session = Depends(get_db)):
    obter_ou_404(db, Disciplina, disciplina_id, "Disciplina")
    return db.scalars(
        select(Disciplina)
        .join(PreRequisito, PreRequisito.requisito_id == Disciplina.id)
        .where(PreRequisito.disciplina_id == disciplina_id)
        .order_by(Disciplina.codigo)
    ).all()


@router.post("/{disciplina_id}/pre-requisitos", response_model=list[DisciplinaOut], status_code=201)
def adicionar_pre_requisito(disciplina_id: int, dados: PreRequisitoCreate, db: Session = Depends(get_db)):
    obter_ou_404(db, Disciplina, disciplina_id, "Disciplina")
    obter_ou_404(db, Disciplina, dados.requisito_id, "Disciplina requisito")
    if dados.requisito_id == disciplina_id:
        raise RegraViolada("PRE_REQUISITO_INVALIDO", "Uma disciplina nao pode ser pre-requisito de si mesma.")
    existe = db.scalar(
        select(PreRequisito.id).where(
            PreRequisito.disciplina_id == disciplina_id,
            PreRequisito.requisito_id == dados.requisito_id,
        )
    )
    if existe:
        raise Conflito("PRE_REQUISITO_DUPLICADO", "Pre-requisito ja cadastrado.")
    if disciplina_id in _requisitos_transitivos(db, dados.requisito_id):
        raise RegraViolada("PRE_REQUISITO_CICLICO", "O pre-requisito criaria uma dependencia circular.")
    db.add(PreRequisito(disciplina_id=disciplina_id, requisito_id=dados.requisito_id))
    db.commit()
    return listar_pre_requisitos(disciplina_id, db)


@router.delete("/{disciplina_id}/pre-requisitos/{requisito_id}", status_code=204)
def remover_pre_requisito(disciplina_id: int, requisito_id: int, db: Session = Depends(get_db)):
    pr = db.scalar(
        select(PreRequisito).where(
            PreRequisito.disciplina_id == disciplina_id, PreRequisito.requisito_id == requisito_id
        )
    )
    if pr is None:
        raise NaoEncontrado("Pre-requisito nao encontrado.")
    db.delete(pr)
    db.commit()
    return Response(status_code=204)
