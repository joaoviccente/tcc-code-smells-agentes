from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.disciplina import Disciplina
from app.models.prerequisito import PreRequisito
from app.schemas.disciplina import (
    DisciplinaCreate,
    DisciplinaUpdate,
    DisciplinaResponse,
    PreRequisitoCreate,
    PreRequisitoItem,
)

router = APIRouter(prefix="/disciplinas", tags=["Disciplinas"])


def formatar_disciplina_response(d: Disciplina, db: Session) -> DisciplinaResponse:
    prereqs = db.query(PreRequisito).filter(PreRequisito.disciplina_id == d.id).all()
    itens_prereq = []
    for p in prereqs:
        pr_disc = db.query(Disciplina).filter(Disciplina.id == p.prerequisito_id).first()
        if pr_disc:
            itens_prereq.append(PreRequisitoItem(id=pr_disc.id, codigo=pr_disc.codigo, nome=pr_disc.nome))

    return DisciplinaResponse(
        id=d.id,
        codigo=d.codigo,
        nome=d.nome,
        numero_creditos=d.numero_creditos,
        carga_horaria=d.carga_horaria,
        departamento=d.departamento,
        pre_requisitos=itens_prereq,
    )


@router.post("", response_model=DisciplinaResponse, status_code=status.HTTP_201_CREATED)
def criar_disciplina(payload: DisciplinaCreate, db: Session = Depends(get_db)):
    if db.query(Disciplina).filter(Disciplina.codigo == payload.codigo.strip().upper()).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Disciplina com código '{payload.codigo}' já existe"
        )

    nova_disc = Disciplina(
        codigo=payload.codigo.strip().upper(),
        nome=payload.nome.strip(),
        numero_creditos=payload.numero_creditos,
        carga_horaria=payload.carga_horaria,
        departamento=payload.departamento.strip().upper(),
    )
    db.add(nova_disc)
    db.commit()
    db.refresh(nova_disc)
    return formatar_disciplina_response(nova_disc, db)


@router.get("", response_model=List[DisciplinaResponse])
def listar_disciplinas(
    departamento: Optional[str] = None,
    termo: Optional[str] = Query(None, description="Busca por nome ou código"),
    db: Session = Depends(get_db)
):
    query = db.query(Disciplina)
    if departamento:
        query = query.filter(Disciplina.departamento == departamento.strip().upper())
    if termo:
        like_termo = f"%{termo.strip()}%"
        query = query.filter((Disciplina.nome.ilike(like_termo)) | (Disciplina.codigo.ilike(like_termo)))

    disciplinas = query.all()
    return [formatar_disciplina_response(d, db) for d in disciplinas]


@router.get("/{id}", response_model=DisciplinaResponse)
def obter_disciplina(id: int, db: Session = Depends(get_db)):
    disciplina = db.query(Disciplina).filter(Disciplina.id == id).first()
    if not disciplina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Disciplina não encontrada")
    return formatar_disciplina_response(disciplina, db)


@router.put("/{id}", response_model=DisciplinaResponse)
def atualizar_disciplina(id: int, payload: DisciplinaUpdate, db: Session = Depends(get_db)):
    disciplina = db.query(Disciplina).filter(Disciplina.id == id).first()
    if not disciplina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Disciplina não encontrada")

    if payload.codigo and payload.codigo.strip().upper() != disciplina.codigo:
        if db.query(Disciplina).filter(Disciplina.codigo == payload.codigo.strip().upper()).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Código de disciplina já existente")
        disciplina.codigo = payload.codigo.strip().upper()

    if payload.nome is not None:
        disciplina.nome = payload.nome.strip()
    if payload.numero_creditos is not None:
        disciplina.numero_creditos = payload.numero_creditos
    if payload.carga_horaria is not None:
        disciplina.carga_horaria = payload.carga_horaria
    if payload.departamento is not None:
        disciplina.departamento = payload.departamento.strip().upper()

    db.commit()
    db.refresh(disciplina)
    return formatar_disciplina_response(disciplina, db)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_disciplina(id: int, db: Session = Depends(get_db)):
    disciplina = db.query(Disciplina).filter(Disciplina.id == id).first()
    if not disciplina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Disciplina não encontrada")
    db.delete(disciplina)
    db.commit()
    return None


@router.post("/{id}/pre-requisitos", response_model=DisciplinaResponse, status_code=status.HTTP_201_CREATED)
def adicionar_prerequisito(id: int, payload: PreRequisitoCreate, db: Session = Depends(get_db)):
    disciplina = db.query(Disciplina).filter(Disciplina.id == id).first()
    if not disciplina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Disciplina não encontrada")

    if id == payload.prerequisito_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uma disciplina não pode ser pré-requisito de si mesma")

    prereq_disc = db.query(Disciplina).filter(Disciplina.id == payload.prerequisito_id).first()
    if not prereq_disc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Disciplina pré-requisito não encontrada")

    existente = db.query(PreRequisito).filter(
        PreRequisito.disciplina_id == id,
        PreRequisito.prerequisito_id == payload.prerequisito_id
    ).first()
    if existente:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pré-requisito já cadastrado para esta disciplina")

    novo_prereq = PreRequisito(disciplina_id=id, prerequisito_id=payload.prerequisito_id)
    db.add(novo_prereq)
    db.commit()
    return formatar_disciplina_response(disciplina, db)


@router.get("/{id}/pre-requisitos", response_model=List[PreRequisitoItem])
def listar_prerequisitos(id: int, db: Session = Depends(get_db)):
    disciplina = db.query(Disciplina).filter(Disciplina.id == id).first()
    if not disciplina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Disciplina não encontrada")

    prereqs = db.query(PreRequisito).filter(PreRequisito.disciplina_id == id).all()
    itens = []
    for p in prereqs:
        pr_disc = db.query(Disciplina).filter(Disciplina.id == p.prerequisito_id).first()
        if pr_disc:
            itens.append(PreRequisitoItem(id=pr_disc.id, codigo=pr_disc.codigo, nome=pr_disc.nome))
    return itens


@router.delete("/{id}/pre-requisitos/{prereq_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_prerequisito(id: int, prereq_id: int, db: Session = Depends(get_db)):
    pr = db.query(PreRequisito).filter(
        PreRequisito.disciplina_id == id,
        PreRequisito.prerequisito_id == prereq_id
    ).first()
    if not pr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vínculo de pré-requisito não encontrado")
    db.delete(pr)
    db.commit()
    return None
