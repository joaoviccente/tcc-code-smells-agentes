from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.disciplina import Disciplina
from app.schemas.disciplina import DisciplinaCreate, DisciplinaUpdate, DisciplinaResponse

router = APIRouter(prefix="/disciplinas", tags=["Disciplinas"])

@router.post("", response_model=DisciplinaResponse, status_code=status.HTTP_201_CREATED)
def criar_disciplina(payload: DisciplinaCreate, db: Session = Depends(get_db)):
    if db.query(Disciplina).filter(Disciplina.codigo == payload.codigo).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Disciplina com código '{payload.codigo}' já existe"
        )

    # Verifica pré-requisitos fornecidos
    pre_reqs = []
    if payload.pre_requisito_ids:
        pre_reqs = db.query(Disciplina).filter(Disciplina.id.in_(payload.pre_requisito_ids)).all()
        if len(pre_reqs) != len(payload.pre_requisito_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Um ou mais IDs de pré-requisitos informados não foram encontrados"
            )

    disciplina = Disciplina(
        codigo=payload.codigo,
        nome=payload.nome,
        numero_creditos=payload.numero_creditos,
        carga_horaria=payload.carga_horaria,
        departamento=payload.departamento,
        pre_requisitos=pre_reqs
    )
    db.add(disciplina)
    db.commit()
    db.refresh(disciplina)
    return disciplina

@router.get("", response_model=List[DisciplinaResponse])
def listar_disciplinas(
    departamento: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(Disciplina)
    if departamento:
        query = query.filter(Disciplina.departamento == departamento)
    return query.all()

@router.get("/{id}", response_model=DisciplinaResponse)
def obter_disciplina(id: int, db: Session = Depends(get_db)):
    disciplina = db.query(Disciplina).filter(Disciplina.id == id).first()
    if not disciplina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Disciplina com ID {id} não encontrada")
    return disciplina

@router.put("/{id}", response_model=DisciplinaResponse)
def atualizar_disciplina(id: int, payload: DisciplinaUpdate, db: Session = Depends(get_db)):
    disciplina = db.query(Disciplina).filter(Disciplina.id == id).first()
    if not disciplina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Disciplina com ID {id} não encontrada")

    update_data = payload.model_dump(exclude_unset=True)
    if "codigo" in update_data and update_data["codigo"] != disciplina.codigo:
        if db.query(Disciplina).filter(Disciplina.codigo == update_data["codigo"]).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Código de disciplina já existente")

    if "pre_requisito_ids" in update_data:
        p_ids = update_data.pop("pre_requisito_ids")
        if p_ids is not None:
            # Não permitir que uma disciplina seja pré-requisito de si mesma
            if id in p_ids:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uma disciplina não pode ser pré-requisito de si mesma")
            reqs = db.query(Disciplina).filter(Disciplina.id.in_(p_ids)).all()
            disciplina.pre_requisitos = reqs

    for k, v in update_data.items():
        setattr(disciplina, k, v)

    db.commit()
    db.refresh(disciplina)
    return disciplina

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_disciplina(id: int, db: Session = Depends(get_db)):
    disciplina = db.query(Disciplina).filter(Disciplina.id == id).first()
    if not disciplina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Disciplina com ID {id} não encontrada")
    db.delete(disciplina)
    db.commit()
    return None

@router.post("/{id}/pre-requisitos/{pre_req_id}", response_model=DisciplinaResponse)
def adicionar_pre_requisito(id: int, pre_req_id: int, db: Session = Depends(get_db)):
    if id == pre_req_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uma disciplina não pode ser pré-requisito de si mesma")

    disciplina = db.query(Disciplina).filter(Disciplina.id == id).first()
    if not disciplina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Disciplina {id} não encontrada")

    pre_req = db.query(Disciplina).filter(Disciplina.id == pre_req_id).first()
    if not pre_req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pré-requisito {pre_req_id} não encontrado")

    if pre_req in disciplina.pre_requisitos:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pré-requisito já vinculado a esta disciplina")

    disciplina.pre_requisitos.append(pre_req)
    db.commit()
    db.refresh(disciplina)
    return disciplina

@router.delete("/{id}/pre-requisitos/{pre_req_id}", response_model=DisciplinaResponse)
def remover_pre_requisito(id: int, pre_req_id: int, db: Session = Depends(get_db)):
    disciplina = db.query(Disciplina).filter(Disciplina.id == id).first()
    if not disciplina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Disciplina {id} não encontrada")

    pre_req = db.query(Disciplina).filter(Disciplina.id == pre_req_id).first()
    if not pre_req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pré-requisito {pre_req_id} não encontrado")

    if pre_req not in disciplina.pre_requisitos:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pré-requisito não estava associado a esta disciplina")

    disciplina.pre_requisitos.remove(pre_req)
    db.commit()
    db.refresh(disciplina)
    return disciplina
