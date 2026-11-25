from typing import List, Optional, Set
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.disciplina import Disciplina, PreRequisito
from app.schemas.disciplina import DisciplinaCreate, DisciplinaUpdate


def get_disciplina_by_id(db: Session, disciplina_id: int) -> Disciplina:
    disciplina = db.query(Disciplina).filter(Disciplina.id == disciplina_id).first()
    if not disciplina:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Disciplina com ID {disciplina_id} não encontrada."
        )
    return disciplina


def get_disciplina_by_codigo(db: Session, codigo: str) -> Optional[Disciplina]:
    return db.query(Disciplina).filter(Disciplina.codigo == codigo).first()


def list_disciplinas(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    departamento: Optional[str] = None
) -> List[Disciplina]:
    query = db.query(Disciplina)
    if departamento:
        query = query.filter(Disciplina.departamento == departamento)
    return query.offset(skip).limit(limit).all()


def create_disciplina(db: Session, data: DisciplinaCreate) -> Disciplina:
    if get_disciplina_by_codigo(db, data.codigo):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe disciplina cadastrada com o código '{data.codigo}'."
        )
    disciplina = Disciplina(
        codigo=data.codigo,
        nome=data.nome,
        numero_creditos=data.numero_creditos,
        carga_horaria=data.carga_horaria,
        departamento=data.departamento,
    )
    db.add(disciplina)
    db.commit()
    db.refresh(disciplina)
    return disciplina


def update_disciplina(db: Session, disciplina_id: int, data: DisciplinaUpdate) -> Disciplina:
    disciplina = get_disciplina_by_id(db, disciplina_id)

    if data.codigo and data.codigo != disciplina.codigo:
        existing = get_disciplina_by_codigo(db, data.codigo)
        if existing and existing.id != disciplina.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Já existe disciplina cadastrada com o código '{data.codigo}'."
            )
        disciplina.codigo = data.codigo

    if data.nome is not None:
        disciplina.nome = data.nome
    if data.numero_creditos is not None:
        disciplina.numero_creditos = data.numero_creditos
    if data.carga_horaria is not None:
        disciplina.carga_horaria = data.carga_horaria
    if data.departamento is not None:
        disciplina.departamento = data.departamento

    db.commit()
    db.refresh(disciplina)
    return disciplina


def delete_disciplina(db: Session, disciplina_id: int) -> None:
    disciplina = get_disciplina_by_id(db, disciplina_id)
    db.delete(disciplina)
    db.commit()


def check_circular_dependency(db: Session, target_disciplina_id: int, candidate_prereq_id: int) -> bool:
    """
    Verifica se adicionar candidate_prereq_id como pré-requisito de target_disciplina_id
    criaria um ciclo. Retorna True se houver ciclo.
    """
    # Se a própria disciplina for colocada como pré-requisito dela mesma:
    if target_disciplina_id == candidate_prereq_id:
        return True

    # Busca em largura (BFS) a partir de candidate_prereq_id para ver se alcança target_disciplina_id
    visited: Set[int] = set()
    queue = [candidate_prereq_id]

    while queue:
        current = queue.pop(0)
        if current == target_disciplina_id:
            return True
        if current not in visited:
            visited.add(current)
            # Buscar pré-requisitos exigidos pela disciplina 'current'
            prereqs = db.query(PreRequisito).filter(PreRequisito.disciplina_id == current).all()
            for p in prereqs:
                if p.pre_requisito_id not in visited:
                    queue.append(p.pre_requisito_id)

    return False


def add_pre_requisito(db: Session, disciplina_id: int, pre_requisito_id: int) -> PreRequisito:
    disciplina = get_disciplina_by_id(db, disciplina_id)
    pre_req = get_disciplina_by_id(db, pre_requisito_id)

    if disciplina.id == pre_req.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uma disciplina não pode ser pré-requisito de si mesma."
        )

    # Verificar se já existe a relação
    existing = db.query(PreRequisito).filter(
        PreRequisito.disciplina_id == disciplina_id,
        PreRequisito.pre_requisito_id == pre_requisito_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{pre_req.codigo}' já é pré-requisito de '{disciplina.codigo}'."
        )

    # Verificar dependência circular
    if check_circular_dependency(db, disciplina_id, pre_requisito_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dependência circular detectada: adicionar '{pre_req.codigo}' como pré-requisito de '{disciplina.codigo}' geraria um ciclo."
        )

    relacao = PreRequisito(disciplina_id=disciplina_id, pre_requisito_id=pre_requisito_id)
    db.add(relacao)
    db.commit()
    db.refresh(relacao)
    return relacao


def remove_pre_requisito(db: Session, disciplina_id: int, pre_requisito_id: int) -> None:
    relacao = db.query(PreRequisito).filter(
        PreRequisito.disciplina_id == disciplina_id,
        PreRequisito.pre_requisito_id == pre_requisito_id
    ).first()
    if not relacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relação de pré-requisito não encontrada."
        )
    db.delete(relacao)
    db.commit()


def get_pre_requisitos_da_disciplina(db: Session, disciplina_id: int) -> List[Disciplina]:
    prereqs = db.query(PreRequisito).filter(PreRequisito.disciplina_id == disciplina_id).all()
    return [p.disciplina_requisito for p in prereqs]
