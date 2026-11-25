from typing import List, Optional
from fastapi import APIRouter, Depends, status, Body
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import EstadoEmprestimo
from app.schemas import (
    EmprestimoCreate,
    EmprestimoDevolver,
    EmprestimoResponse,
)
import app.services as services

router = APIRouter(prefix="/emprestimos", tags=["Empréstimos"])

@router.post("", response_model=EmprestimoResponse, status_code=status.HTTP_201_CREATED)
def criar_emprestimo(dados: EmprestimoCreate, db: Session = Depends(get_db)):
    return services.criar_emprestimo(
        db,
        usuario_id=dados.usuario_id,
        exemplar_id=dados.exemplar_id,
        data_retirada=dados.data_retirada,
    )

@router.get("", response_model=List[EmprestimoResponse], status_code=status.HTTP_200_OK)
def listar_emprestimos(
    usuario_id: Optional[int] = None,
    estado: Optional[EstadoEmprestimo] = None,
    db: Session = Depends(get_db)
):
    return services.get_emprestimos(db, usuario_id=usuario_id, estado=estado)

@router.get("/{emprestimo_id}", response_model=EmprestimoResponse, status_code=status.HTTP_200_OK)
def buscar_emprestimo(emprestimo_id: int, db: Session = Depends(get_db)):
    return services.get_emprestimo(db, emprestimo_id)

@router.post("/{emprestimo_id}/renovar", response_model=EmprestimoResponse, status_code=status.HTTP_200_OK)
def renovar_emprestimo(emprestimo_id: int, db: Session = Depends(get_db)):
    return services.renovar_emprestimo(db, emprestimo_id)

@router.post("/{emprestimo_id}/devolver", response_model=EmprestimoResponse, status_code=status.HTTP_200_OK)
def devolver_emprestimo(
    emprestimo_id: int,
    dados: Optional[EmprestimoDevolver] = None,
    db: Session = Depends(get_db)
):
    data_devolucao = dados.data_devolucao if dados else None
    return services.devolver_emprestimo(db, emprestimo_id, data_devolucao=data_devolucao)
