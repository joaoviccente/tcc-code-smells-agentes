from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import EstadoExemplar
from app.schemas import ExemplarCreate, ExemplarUpdate, ExemplarResponse
import app.services as services

router = APIRouter(prefix="/exemplares", tags=["Exemplares"])

@router.post("", response_model=ExemplarResponse, status_code=status.HTTP_201_CREATED)
def criar_exemplar(exemplar: ExemplarCreate, db: Session = Depends(get_db)):
    return services.criar_exemplar(db, exemplar)

@router.get("", response_model=List[ExemplarResponse], status_code=status.HTTP_200_OK)
def listar_exemplares(
    livro_id: Optional[int] = None,
    estado: Optional[EstadoExemplar] = None,
    db: Session = Depends(get_db)
):
    return services.get_exemplares(db, livro_id=livro_id, estado=estado)

@router.get("/{exemplar_id}", response_model=ExemplarResponse, status_code=status.HTTP_200_OK)
def buscar_exemplar(exemplar_id: int, db: Session = Depends(get_db)):
    return services.get_exemplar(db, exemplar_id)

@router.put("/{exemplar_id}", response_model=ExemplarResponse, status_code=status.HTTP_200_OK)
def atualizar_exemplar(exemplar_id: int, dados: ExemplarUpdate, db: Session = Depends(get_db)):
    return services.atualizar_exemplar(db, exemplar_id, dados)

@router.delete("/{exemplar_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_exemplar(exemplar_id: int, db: Session = Depends(get_db)):
    services.deletar_exemplar(db, exemplar_id)
    return None
