from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.enums import EstadoEmprestimo
from app.schemas.emprestimo import (
    EmprestimoCreate,
    EmprestimoDevolver,
    EmprestimoRenovar,
    EmprestimoResponse,
)
from app.services import emprestimo_service

router = APIRouter(prefix="/emprestimos", tags=["Empréstimos"])


@router.post("", response_model=EmprestimoResponse, status_code=status.HTTP_201_CREATED)
def criar_emprestimo(emp_in: EmprestimoCreate, db: Session = Depends(get_db)):
    return emprestimo_service.create_emprestimo(db, emp_in)


@router.post("/{emprestimo_id}/renovar", response_model=EmprestimoResponse)
def renovar_emprestimo(
    emprestimo_id: int,
    renovar_in: Optional[EmprestimoRenovar] = None,
    db: Session = Depends(get_db),
):
    return emprestimo_service.renovar_emprestimo(db, emprestimo_id, renovar_in)


@router.post("/{emprestimo_id}/devolver", response_model=EmprestimoResponse)
def devolver_emprestimo(
    emprestimo_id: int,
    devolver_in: Optional[EmprestimoDevolver] = None,
    db: Session = Depends(get_db),
):
    return emprestimo_service.devolver_emprestimo(db, emprestimo_id, devolver_in)


@router.get("/usuario/{usuario_id}", response_model=List[EmprestimoResponse])
def listar_emprestimos_por_usuario(
    usuario_id: int,
    data_referencia: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    return emprestimo_service.list_emprestimos_usuario(
        db, usuario_id, data_referencia=data_referencia
    )


@router.get("", response_model=List[EmprestimoResponse])
def listar_todos_emprestimos(
    usuario_id: Optional[int] = None,
    exemplar_id: Optional[int] = None,
    estado: Optional[EstadoEmprestimo] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return emprestimo_service.list_emprestimos(
        db,
        usuario_id=usuario_id,
        exemplar_id=exemplar_id,
        estado=estado,
        skip=skip,
        limit=limit,
    )


@router.get("/{emprestimo_id}", response_model=EmprestimoResponse)
def obter_emprestimo(emprestimo_id: int, db: Session = Depends(get_db)):
    return emprestimo_service.get_emprestimo(db, emprestimo_id)
