from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.enums import EstadoEmprestimo
from app.schemas.emprestimo import (
    EmprestimoCreate,
    EmprestimoRenovar,
    EmprestimoDevolver,
    EmprestimoResponse,
)
from app.services import emprestimo_service

router = APIRouter(prefix="/emprestimos", tags=["Empréstimos"])


@router.post("", response_model=EmprestimoResponse, status_code=status.HTTP_201_CREATED)
def criar_emprestimo(emprestimo_in: EmprestimoCreate, db: Session = Depends(get_db)):
    """Cria um novo empréstimo respeitando todas as regras de negócio."""
    return emprestimo_service.create_emprestimo(db, emprestimo_in)


@router.post("/{id}/renovar", response_model=EmprestimoResponse, status_code=status.HTTP_200_OK)
def renovar_emprestimo(
    id: int, renovar_in: Optional[EmprestimoRenovar] = None, db: Session = Depends(get_db)
):
    """Renova um empréstimo ativo."""
    data_renovacao = renovar_in.data_renovacao if renovar_in else None
    return emprestimo_service.renovar_emprestimo(db, id, data_renovacao=data_renovacao)


@router.post("/{id}/devolver", response_model=EmprestimoResponse, status_code=status.HTTP_200_OK)
def devolver_emprestimo(
    id: int, devolver_in: Optional[EmprestimoDevolver] = None, db: Session = Depends(get_db)
):
    """Devolve um exemplar emprestado, calculando multas e atualizando suspensões e reservas."""
    data_devolucao = devolver_in.data_devolucao if devolver_in else None
    return emprestimo_service.devolver_emprestimo(db, id, data_devolucao=data_devolucao)


@router.get("", response_model=List[EmprestimoResponse], status_code=status.HTTP_200_OK)
def listar_emprestimos(
    usuario_id: Optional[int] = None,
    exemplar_id: Optional[int] = None,
    estado: Optional[EstadoEmprestimo] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return emprestimo_service.get_emprestimos(
        db, usuario_id=usuario_id, exemplar_id=exemplar_id, estado=estado, skip=skip, limit=limit
    )


@router.get("/usuario/{usuario_id}", response_model=List[EmprestimoResponse], status_code=status.HTTP_200_OK)
def listar_emprestimos_por_usuario(usuario_id: int, db: Session = Depends(get_db)):
    """Listar empréstimos por usuário."""
    return emprestimo_service.get_emprestimos(db, usuario_id=usuario_id)


@router.get("/{id}", response_model=EmprestimoResponse, status_code=status.HTTP_200_OK)
def obter_emprestimo(id: int, db: Session = Depends(get_db)):
    return emprestimo_service.get_emprestimo_by_id(db, id)
