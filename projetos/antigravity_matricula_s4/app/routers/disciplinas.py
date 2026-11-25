from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.disciplina import (
    DisciplinaCreate,
    DisciplinaUpdate,
    DisciplinaResponse,
    PreRequisitoCreate,
    PreRequisitoItem,
)
from app.services import disciplina_service

router = APIRouter(prefix="/disciplinas", tags=["Disciplinas"])


def format_disciplina_response(d) -> DisciplinaResponse:
    prereqs = [
        PreRequisitoItem(
            id=p.disciplina_requisito.id,
            codigo=p.disciplina_requisito.codigo,
            nome=p.disciplina_requisito.nome,
        )
        for p in d.pre_requisitos
    ]
    return DisciplinaResponse(
        id=d.id,
        codigo=d.codigo,
        nome=d.nome,
        numero_creditos=d.numero_creditos,
        carga_horaria=d.carga_horaria,
        departamento=d.departamento,
        pre_requisitos=prereqs,
    )


@router.post("", response_model=DisciplinaResponse, status_code=status.HTTP_201_CREATED)
def criar_disciplina(data: DisciplinaCreate, db: Session = Depends(get_db)):
    disciplina = disciplina_service.create_disciplina(db, data)
    return format_disciplina_response(disciplina)


@router.get("", response_model=List[DisciplinaResponse])
def listar_disciplinas(
    skip: int = 0,
    limit: int = 100,
    departamento: Optional[str] = None,
    db: Session = Depends(get_db)
):
    disciplinas = disciplina_service.list_disciplinas(db, skip=skip, limit=limit, departamento=departamento)
    return [format_disciplina_response(d) for d in disciplinas]


@router.get("/{disciplina_id}", response_model=DisciplinaResponse)
def obter_disciplina(disciplina_id: int, db: Session = Depends(get_db)):
    disciplina = disciplina_service.get_disciplina_by_id(db, disciplina_id)
    return format_disciplina_response(disciplina)


@router.put("/{disciplina_id}", response_model=DisciplinaResponse)
def atualizar_disciplina(disciplina_id: int, data: DisciplinaUpdate, db: Session = Depends(get_db)):
    disciplina = disciplina_service.update_disciplina(db, disciplina_id, data)
    return format_disciplina_response(disciplina)


@router.delete("/{disciplina_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_disciplina(disciplina_id: int, db: Session = Depends(get_db)):
    disciplina_service.delete_disciplina(db, disciplina_id)
    return None


@router.post("/{disciplina_id}/pre-requisitos", response_model=PreRequisitoItem, status_code=status.HTTP_201_CREATED)
def adicionar_pre_requisito(
    disciplina_id: int,
    data: PreRequisitoCreate,
    db: Session = Depends(get_db)
):
    relacao = disciplina_service.add_pre_requisito(db, disciplina_id, data.pre_requisito_id)
    return PreRequisitoItem(
        id=relacao.disciplina_requisito.id,
        codigo=relacao.disciplina_requisito.codigo,
        nome=relacao.disciplina_requisito.nome,
    )


@router.get("/{disciplina_id}/pre-requisitos", response_model=List[PreRequisitoItem])
def listar_pre_requisitos(disciplina_id: int, db: Session = Depends(get_db)):
    prereqs = disciplina_service.get_pre_requisitos_da_disciplina(db, disciplina_id)
    return [
        PreRequisitoItem(id=p.id, codigo=p.codigo, nome=p.nome)
        for p in prereqs
    ]


@router.delete("/{disciplina_id}/pre-requisitos/{pre_requisito_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_pre_requisito(disciplina_id: int, pre_requisito_id: int, db: Session = Depends(get_db)):
    disciplina_service.remove_pre_requisito(db, disciplina_id, pre_requisito_id)
    return None
