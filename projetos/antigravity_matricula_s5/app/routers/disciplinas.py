from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.disciplina import Disciplina
from app.models.prerequisito import PreRequisito
from app.schemas.disciplina import (
    DisciplinaCreate,
    DisciplinaUpdate,
    DisciplinaResponse,
    DisciplinaSimple,
)

router = APIRouter(prefix="/disciplinas", tags=["Disciplinas"])


@router.post("", response_model=DisciplinaResponse, status_code=status.HTTP_201_CREATED)
def criar_disciplina(payload: DisciplinaCreate, db: Session = Depends(get_db)):
    """Cria uma nova disciplina, opcionalmente associando pré-requisitos."""
    # Verificar unicidade do código
    if db.query(Disciplina).filter(Disciplina.codigo == payload.codigo).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe disciplina cadastrada com o código '{payload.codigo}'."
        )

    nova_disciplina = Disciplina(
        codigo=payload.codigo,
        nome=payload.nome,
        numero_creditos=payload.numero_creditos,
        carga_horaria=payload.carga_horaria,
        departamento=payload.departamento,
    )
    db.add(nova_disciplina)
    db.flush()

    # Associar pré-requisitos se fornecidos
    if payload.prerequisitos_ids:
        for pre_id in payload.prerequisitos_ids:
            if pre_id == nova_disciplina.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uma disciplina não pode ter a si mesma como pré-requisito."
                )
            pre_disc = db.query(Disciplina).filter(Disciplina.id == pre_id).first()
            if not pre_disc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Disciplina de pré-requisito com ID {pre_id} não encontrada."
                )
            nova_disciplina.prerequisitos.append(pre_disc)

    db.commit()
    db.refresh(nova_disciplina)
    return nova_disciplina


@router.get("", response_model=List[DisciplinaResponse])
def listar_disciplinas(
    departamento: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Lista todas as disciplinas, com filtro opcional por departamento."""
    query = db.query(Disciplina)
    if departamento:
        query = query.filter(Disciplina.departamento == departamento)
    return query.all()


@router.get("/{disciplina_id}", response_model=DisciplinaResponse)
def obter_disciplina(disciplina_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de uma disciplina e seus pré-requisitos."""
    disciplina = db.query(Disciplina).filter(Disciplina.id == disciplina_id).first()
    if not disciplina:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Disciplina com ID {disciplina_id} não encontrada."
        )
    return disciplina


@router.put("/{disciplina_id}", response_model=DisciplinaResponse)
def atualizar_disciplina(
    disciplina_id: int,
    payload: DisciplinaUpdate,
    db: Session = Depends(get_db)
):
    """Atualiza dados cadastrais e lista de pré-requisitos de uma disciplina."""
    disciplina = db.query(Disciplina).filter(Disciplina.id == disciplina_id).first()
    if not disciplina:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Disciplina com ID {disciplina_id} não encontrada."
        )

    update_data = payload.model_dump(exclude_unset=True)
    if "codigo" in update_data:
        codigo_existente = (
            db.query(Disciplina)
            .filter(Disciplina.codigo == update_data["codigo"], Disciplina.id != disciplina_id)
            .first()
        )
        if codigo_existente:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Código '{update_data['codigo']}' já está em uso por outra disciplina."
            )

    if "prerequisitos_ids" in update_data:
        prereqs_ids = update_data.pop("prerequisitos_ids")
        if prereqs_ids is not None:
            if disciplina_id in prereqs_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uma disciplina não pode ter a si mesma como pré-requisito."
                )
            disciplinas_prereq = (
                db.query(Disciplina)
                .filter(Disciplina.id.in_(prereqs_ids))
                .all()
            )
            if len(disciplinas_prereq) != len(prereqs_ids):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Um ou mais IDs de pré-requisitos fornecidos não existem."
                )
            disciplina.prerequisitos = disciplinas_prereq

    for field, value in update_data.items():
        setattr(disciplina, field, value)

    db.commit()
    db.refresh(disciplina)
    return disciplina


@router.delete("/{disciplina_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_disciplina(disciplina_id: int, db: Session = Depends(get_db)):
    """Remove uma disciplina do sistema."""
    disciplina = db.query(Disciplina).filter(Disciplina.id == disciplina_id).first()
    if not disciplina:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Disciplina com ID {disciplina_id} não encontrada."
        )
    db.delete(disciplina)
    db.commit()
    return None


@router.post("/{disciplina_id}/prerequisitos/{prereq_id}", status_code=status.HTTP_201_CREATED)
def adicionar_prerequisito(
    disciplina_id: int,
    prereq_id: int,
    db: Session = Depends(get_db)
):
    """Adiciona um pré-requisito a uma disciplina."""
    if disciplina_id == prereq_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uma disciplina não pode ser pré-requisito de si mesma."
        )
    disciplina = db.query(Disciplina).filter(Disciplina.id == disciplina_id).first()
    if not disciplina:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Disciplina {disciplina_id} não encontrada."
        )
    prereq = db.query(Disciplina).filter(Disciplina.id == prereq_id).first()
    if not prereq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Disciplina de pré-requisito {prereq_id} não encontrada."
        )

    if prereq in disciplina.prerequisitos:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A disciplina '{prereq.nome}' já é pré-requisito desta disciplina."
        )

    disciplina.prerequisitos.append(prereq)
    db.commit()
    return {"mensagem": f"Pré-requisito '{prereq.nome}' adicionado com sucesso a '{disciplina.nome}'."}


@router.delete("/{disciplina_id}/prerequisitos/{prereq_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_prerequisito(
    disciplina_id: int,
    prereq_id: int,
    db: Session = Depends(get_db)
):
    """Remove um pré-requisito de uma disciplina."""
    disciplina = db.query(Disciplina).filter(Disciplina.id == disciplina_id).first()
    if not disciplina:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Disciplina {disciplina_id} não encontrada."
        )
    prereq = db.query(Disciplina).filter(Disciplina.id == prereq_id).first()
    if not prereq:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Disciplina {prereq_id} não encontrada."
        )

    if prereq not in disciplina.prerequisitos:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="O pré-requisito informado não está vinculado a esta disciplina."
        )

    disciplina.prerequisitos.remove(prereq)
    db.commit()
    return None
