from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.config import EstadoEmprestimo
from app.database import get_db
from app.schemas.emprestimo import (
    EmprestimoCreate,
    EmprestimoDevolucao,
    EmprestimoResponse,
)
from app.services import emprestimo_service

router = APIRouter(prefix="/emprestimos", tags=["Empréstimos"])


@router.post("", response_model=EmprestimoResponse, status_code=status.HTTP_201_CREATED)
def criar_emprestimo(emprestimo_in: EmprestimoCreate, db: Session = Depends(get_db)):
    return emprestimo_service.criar_emprestimo(db, emprestimo_in)


@router.post("/{emprestimo_id}/renovar", response_model=EmprestimoResponse)
def renovar_emprestimo(emprestimo_id: int, db: Session = Depends(get_db)):
    return emprestimo_service.renovar_emprestimo(db, emprestimo_id)


@router.post("/{emprestimo_id}/devolver", response_model=EmprestimoResponse)
def devolver_emprestimo(
    emprestimo_id: int,
    devolucao_in: EmprestimoDevolucao | None = None,
    db: Session = Depends(get_db),
):
    return emprestimo_service.devolver_emprestimo(db, emprestimo_id, devolucao_in)


@router.get("/usuario/{usuario_id}", response_model=list[EmprestimoResponse])
def listar_por_usuario(usuario_id: int, db: Session = Depends(get_db)):
    return emprestimo_service.listar_emprestimos_por_usuario(db, usuario_id)


@router.get("", response_model=list[EmprestimoResponse])
def listar_todos_emprestimos(
    estado: EstadoEmprestimo | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return emprestimo_service.listar_todos_emprestimos(db, estado=estado, skip=skip, limit=limit)
