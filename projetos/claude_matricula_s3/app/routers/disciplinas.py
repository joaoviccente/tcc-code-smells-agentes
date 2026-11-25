from typing import Optional

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from .. import errors, schemas
from ..database import get_db
from ..deps import paginacao
from ..models import Disciplina, Historico, PreRequisito, Turma

router = APIRouter(prefix="/disciplinas", tags=["Disciplinas"])


def obter_disciplina(db: Session, disciplina_id: int) -> Disciplina:
    d = db.get(Disciplina, disciplina_id)
    if d is None:
        raise errors.nao_encontrado("Disciplina", disciplina_id)
    return d


def _saida(d: Disciplina) -> schemas.DisciplinaOut:
    return schemas.DisciplinaOut(
        id=d.id,
        codigo=d.codigo,
        nome=d.nome,
        creditos=d.creditos,
        carga_horaria=d.carga_horaria,
        departamento=d.departamento,
        pre_requisitos=[schemas.DisciplinaResumo.model_validate(p.requisito) for p in d.pre_requisitos],
    )


def _codigo_unico(db: Session, codigo: str, ignorar_id=None):
    q = select(Disciplina.id).where(Disciplina.codigo == codigo)
    if ignorar_id is not None:
        q = q.where(Disciplina.id != ignorar_id)
    if db.scalar(q):
        raise errors.conflito("DISCIPLINA_DUPLICADA", f"Já existe disciplina com código {codigo}.")


@router.post("", response_model=schemas.DisciplinaOut, status_code=status.HTTP_201_CREATED)
def criar_disciplina(dados: schemas.DisciplinaCreate, db: Session = Depends(get_db)):
    _codigo_unico(db, dados.codigo)
    d = Disciplina(**dados.model_dump())
    db.add(d)
    db.commit()
    return _saida(d)


@router.get("", response_model=list[schemas.DisciplinaOut])
def listar_disciplinas(
    departamento: Optional[str] = None,
    pag: tuple[int, int] = Depends(paginacao),
    db: Session = Depends(get_db),
):
    q = select(Disciplina).order_by(Disciplina.codigo)
    if departamento:
        q = q.where(Disciplina.departamento == departamento)
    return [_saida(d) for d in db.scalars(q.offset(pag[0]).limit(pag[1])).all()]


@router.get("/{disciplina_id}", response_model=schemas.DisciplinaOut)
def obter(disciplina_id: int, db: Session = Depends(get_db)):
    return _saida(obter_disciplina(db, disciplina_id))


@router.patch("/{disciplina_id}", response_model=schemas.DisciplinaOut)
def atualizar_disciplina(
    disciplina_id: int, dados: schemas.DisciplinaUpdate, db: Session = Depends(get_db)
):
    d = obter_disciplina(db, disciplina_id)
    valores = dados.model_dump(exclude_unset=True)
    if "codigo" in valores:
        _codigo_unico(db, valores["codigo"], ignorar_id=d.id)
    for k, v in valores.items():
        setattr(d, k, v)
    db.commit()
    return _saida(d)


@router.delete("/{disciplina_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_disciplina(disciplina_id: int, db: Session = Depends(get_db)):
    d = obter_disciplina(db, disciplina_id)
    em_uso = (
        db.scalar(select(exists().where(Turma.disciplina_id == d.id)))
        or db.scalar(select(exists().where(Historico.disciplina_id == d.id)))
        or db.scalar(select(exists().where(PreRequisito.requisito_id == d.id)))
    )
    if em_uso:
        raise errors.conflito(
            "DISCIPLINA_EM_USO",
            "Disciplina possui turmas, histórico ou é pré-requisito de outra e não pode ser removida.",
        )
    db.delete(d)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------- pré-requisitos
def _depende_de(db: Session, origem_id: int, alvo_id: int) -> bool:
    """True se `origem` exige (direta ou indiretamente) `alvo`."""
    visitados, pilha = set(), [origem_id]
    while pilha:
        atual = pilha.pop()
        if atual == alvo_id:
            return True
        if atual in visitados:
            continue
        visitados.add(atual)
        pilha.extend(
            db.scalars(select(PreRequisito.requisito_id).where(PreRequisito.disciplina_id == atual))
        )
    return False


@router.get("/{disciplina_id}/pre-requisitos", response_model=list[schemas.DisciplinaResumo])
def listar_pre_requisitos(disciplina_id: int, db: Session = Depends(get_db)):
    d = obter_disciplina(db, disciplina_id)
    return [p.requisito for p in d.pre_requisitos]


@router.post(
    "/{disciplina_id}/pre-requisitos",
    response_model=schemas.DisciplinaOut,
    status_code=status.HTTP_201_CREATED,
)
def adicionar_pre_requisito(
    disciplina_id: int, dados: schemas.PreRequisitoCreate, db: Session = Depends(get_db)
):
    d = obter_disciplina(db, disciplina_id)
    obter_disciplina(db, dados.requisito_id)
    if dados.requisito_id == d.id:
        raise errors.regra("PRE_REQUISITO_INVALIDO", "Uma disciplina não pode exigir a si mesma.")
    if any(p.requisito_id == dados.requisito_id for p in d.pre_requisitos):
        raise errors.conflito("PRE_REQUISITO_DUPLICADO", "Pré-requisito já cadastrado.")
    if _depende_de(db, dados.requisito_id, d.id):
        raise errors.regra(
            "PRE_REQUISITO_CICLICO", "O pré-requisito criaria uma dependência circular."
        )
    d.pre_requisitos.append(PreRequisito(requisito_id=dados.requisito_id))
    db.commit()
    db.refresh(d)
    return _saida(d)


@router.delete(
    "/{disciplina_id}/pre-requisitos/{requisito_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remover_pre_requisito(disciplina_id: int, requisito_id: int, db: Session = Depends(get_db)):
    obter_disciplina(db, disciplina_id)
    pr = db.scalar(
        select(PreRequisito).where(
            PreRequisito.disciplina_id == disciplina_id, PreRequisito.requisito_id == requisito_id
        )
    )
    if pr is None:
        raise errors.nao_encontrado("Pré-requisito", requisito_id)
    db.delete(pr)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
