from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.database import get_db
from app.errors import ErroNegocio
from app.models import Disciplina, Historico, PreRequisito
from app.schemas import DisciplinaCreate, DisciplinaOut, DisciplinaUpdate, PreRequisitoIn

router = APIRouter(prefix="/disciplinas", tags=["disciplinas"])


def _cria_ciclo(db: Session, disciplina_id: int, requisito_id: int) -> bool:
    """Verifica se 'requisito' ja depende (direta ou indiretamente) de 'disciplina'."""
    pendentes, vistos = [requisito_id], set()
    while pendentes:
        atual = pendentes.pop()
        if atual == disciplina_id:
            return True
        if atual in vistos:
            continue
        vistos.add(atual)
        pendentes.extend(db.scalars(
            select(PreRequisito.requisito_id).where(PreRequisito.disciplina_id == atual)).all())
    return False


def _adicionar_requisito(db: Session, disciplina: Disciplina, requisito_id: int) -> PreRequisito:
    if requisito_id == disciplina.id:
        raise ErroNegocio(422, "pre_requisito_invalido", "Disciplina nao pode ser pre-requisito de si mesma")
    services.obter(db, Disciplina, requisito_id, "disciplina")
    if any(p.requisito_id == requisito_id for p in disciplina.pre_requisitos):
        raise ErroNegocio(409, "pre_requisito_duplicado", "Pre-requisito ja cadastrado")
    if _cria_ciclo(db, disciplina.id, requisito_id):
        raise ErroNegocio(422, "pre_requisito_ciclico", "Pre-requisito criaria dependencia circular")
    p = PreRequisito(disciplina=disciplina, requisito_id=requisito_id)
    db.add(p)
    db.flush()
    return p


@router.post("", response_model=DisciplinaOut, status_code=status.HTTP_201_CREATED)
def criar(dados: DisciplinaCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Disciplina).where(Disciplina.codigo == dados.codigo)):
        raise ErroNegocio(409, "codigo_ja_cadastrado", f"Ja existe disciplina com codigo '{dados.codigo}'")
    d = Disciplina(**dados.model_dump(exclude={"pre_requisitos"}))
    db.add(d)
    db.flush()
    for rid in dict.fromkeys(dados.pre_requisitos):
        _adicionar_requisito(db, d, rid)
    db.commit()
    return d


@router.get("", response_model=list[DisciplinaOut])
def listar(departamento: str | None = None, offset: int = Query(0, ge=0),
           limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    q = select(Disciplina).order_by(Disciplina.codigo)
    if departamento:
        q = q.where(Disciplina.departamento == departamento)
    return db.scalars(q.offset(offset).limit(limit)).all()


@router.get("/{disciplina_id}", response_model=DisciplinaOut)
def obter(disciplina_id: int, db: Session = Depends(get_db)):
    return services.obter(db, Disciplina, disciplina_id, "disciplina")


@router.patch("/{disciplina_id}", response_model=DisciplinaOut)
@router.put("/{disciplina_id}", response_model=DisciplinaOut, include_in_schema=False)
def atualizar(disciplina_id: int, dados: DisciplinaUpdate, db: Session = Depends(get_db)):
    d = services.obter(db, Disciplina, disciplina_id, "disciplina")
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        if valor is None:
            raise ErroNegocio(422, "valor_nulo", f"Campo '{campo}' nao pode ser nulo")
        setattr(d, campo, valor)
    db.commit()
    return d


@router.delete("/{disciplina_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(disciplina_id: int, db: Session = Depends(get_db)):
    d = services.obter(db, Disciplina, disciplina_id, "disciplina")
    if d.turmas:
        raise ErroNegocio(409, "disciplina_com_turmas", "Disciplina possui turmas cadastradas")
    if db.scalar(select(PreRequisito).where(PreRequisito.requisito_id == d.id)):
        raise ErroNegocio(409, "disciplina_e_pre_requisito", "Disciplina e pre-requisito de outra disciplina")
    if db.scalar(select(Historico).where(Historico.disciplina_id == d.id)):
        raise ErroNegocio(409, "disciplina_com_historico", "Disciplina possui registros de historico")
    db.delete(d)
    db.commit()
    return Response(status_code=204)


@router.post("/{disciplina_id}/pre-requisitos", response_model=DisciplinaOut, status_code=status.HTTP_201_CREATED)
def adicionar_pre_requisito(disciplina_id: int, dados: PreRequisitoIn, db: Session = Depends(get_db)):
    d = services.obter(db, Disciplina, disciplina_id, "disciplina")
    _adicionar_requisito(db, d, dados.requisito_id)
    db.commit()
    db.refresh(d)
    return d


@router.delete("/{disciplina_id}/pre-requisitos/{requisito_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_pre_requisito(disciplina_id: int, requisito_id: int, db: Session = Depends(get_db)):
    services.obter(db, Disciplina, disciplina_id, "disciplina")
    p = db.scalar(select(PreRequisito).where(PreRequisito.disciplina_id == disciplina_id,
                                              PreRequisito.requisito_id == requisito_id))
    if p is None:
        raise ErroNegocio(404, "pre_requisito_nao_encontrado", "Pre-requisito nao encontrado")
    db.delete(p)
    db.commit()
    return Response(status_code=204)
