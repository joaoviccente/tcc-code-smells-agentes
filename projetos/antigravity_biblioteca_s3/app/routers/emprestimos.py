from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.enums import EstadoEmprestimo
from app.schemas.emprestimo import (
    EmprestimoCreate,
    EmprestimoDevolucao,
    EmprestimoResponse,
)
from app.services import emprestimo_service

router = APIRouter(prefix="/emprestimos", tags=["Empréstimos"])


@router.post("", response_model=EmprestimoResponse, status_code=status.HTTP_201_CREATED)
def criar_emprestimo(emprestimo_in: EmprestimoCreate, db: Session = Depends(get_db)):
    """
    Cria um novo empréstimo de exemplar para um usuário.
    Respeita limites da categoria, verificação de suspensão, multas em aberto e reservas.
    """
    return emprestimo_service.create_emprestimo(db, emprestimo_in)


@router.post("/{id}/renovar", response_model=EmprestimoResponse)
def renovar_emprestimo(id: int, db: Session = Depends(get_db)):
    """
    Renova o prazo do empréstimo caso não haja reservas, o empréstimo não esteja em atraso
    e o usuário não tenha atingido o limite de renovações de sua categoria.
    """
    return emprestimo_service.renovar_emprestimo(db, id)


@router.post("/{id}/devolver", response_model=EmprestimoResponse)
def devolver_emprestimo(
    id: int,
    devolucao_in: Optional[EmprestimoDevolucao] = None,
    db: Session = Depends(get_db)
):
    """
    Registra a devolução do exemplar.
    Calcula multas por atraso, regras de perdão para professores, suspensão por atraso > 15 dias,
    baixa de exemplar por atraso > 60 dias e ativação de reservas na fila.
    """
    return emprestimo_service.devolver_emprestimo(db, id, devolucao_in=devolucao_in)


@router.get("/usuario/{usuario_id}", response_model=List[EmprestimoResponse])
def listar_emprestimos_por_usuario(
    usuario_id: int,
    apenas_ativos: bool = Query(False, description="Listar apenas empréstimos em andamento"),
    db: Session = Depends(get_db)
):
    """Lista todos os empréstimos associados a um usuário específico."""
    return emprestimo_service.get_emprestimos_por_usuario(db, usuario_id, apenas_ativos=apenas_ativos)


@router.get("", response_model=List[EmprestimoResponse])
def listar_todos_emprestimos(
    usuario_id: Optional[int] = Query(None),
    exemplar_id: Optional[int] = Query(None),
    estado: Optional[EstadoEmprestimo] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Lista empréstimos com opções de filtros."""
    return emprestimo_service.get_emprestimos(
        db, usuario_id=usuario_id, exemplar_id=exemplar_id, estado=estado, skip=skip, limit=limit
    )


@router.get("/{id}", response_model=EmprestimoResponse)
def obter_emprestimo(id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de um empréstimo específico."""
    return emprestimo_service.get_emprestimo_by_id(db, id)
