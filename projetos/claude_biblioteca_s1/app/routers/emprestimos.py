from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import servicos
from app.deps import get_db
from app.models import Emprestimo, EstadoEmprestimo
from app.schemas import EmprestimoCriar, EmprestimoSaida

router = APIRouter(prefix="/emprestimos", tags=["Emprestimos"])


@router.post("", response_model=EmprestimoSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: EmprestimoCriar, db: Session = Depends(get_db)):
    return servicos.criar_emprestimo(db, dados.usuario_id, dados.exemplar_id)


@router.get("", response_model=list[EmprestimoSaida])
def listar(usuario_id: int | None = None, estado: EstadoEmprestimo | None = None,
           offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    q = select(Emprestimo).order_by(Emprestimo.id)
    if usuario_id is not None:
        q = q.where(Emprestimo.usuario_id == usuario_id)
    if estado:
        q = q.where(Emprestimo.estado == estado)
    return db.scalars(q.offset(offset).limit(limit)).all()


@router.get("/{emprestimo_id}", response_model=EmprestimoSaida)
def detalhar(emprestimo_id: int, db: Session = Depends(get_db)):
    return servicos.obter(db, Emprestimo, emprestimo_id, "Emprestimo")


@router.post("/{emprestimo_id}/renovacao", response_model=EmprestimoSaida)
def renovar(emprestimo_id: int, db: Session = Depends(get_db)):
    return servicos.renovar_emprestimo(db, servicos.obter(db, Emprestimo, emprestimo_id, "Emprestimo"))


@router.post("/{emprestimo_id}/devolucao", response_model=EmprestimoSaida)
def devolver(emprestimo_id: int, db: Session = Depends(get_db)):
    return servicos.devolver_emprestimo(db, servicos.obter(db, Emprestimo, emprestimo_id, "Emprestimo"))
