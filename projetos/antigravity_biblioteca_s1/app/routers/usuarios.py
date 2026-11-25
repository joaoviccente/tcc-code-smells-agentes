from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import CategoriaUsuario, SituacaoUsuario
from app.schemas import (
    UsuarioCreate,
    UsuarioUpdate,
    UsuarioResponse,
    EmprestimoResponse,
    MultaResponse,
)
import app.services as services

router = APIRouter(prefix="/usuarios", tags=["Usuários"])

@router.post("", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
def criar_usuario(usuario: UsuarioCreate, db: Session = Depends(get_db)):
    return services.criar_usuario(db, usuario)

@router.get("", response_model=List[UsuarioResponse], status_code=status.HTTP_200_OK)
def listar_usuarios(
    categoria: Optional[CategoriaUsuario] = None,
    situacao: Optional[SituacaoUsuario] = None,
    db: Session = Depends(get_db)
):
    return services.get_usuarios(db, categoria=categoria, situacao=situacao)

@router.get("/{usuario_id}", response_model=UsuarioResponse, status_code=status.HTTP_200_OK)
def buscar_usuario(usuario_id: int, db: Session = Depends(get_db)):
    return services.get_usuario(db, usuario_id)

@router.put("/{usuario_id}", response_model=UsuarioResponse, status_code=status.HTTP_200_OK)
def atualizar_usuario(usuario_id: int, dados: UsuarioUpdate, db: Session = Depends(get_db)):
    return services.atualizar_usuario(db, usuario_id, dados)

@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_usuario(usuario_id: int, db: Session = Depends(get_db)):
    services.deletar_usuario(db, usuario_id)
    return None

@router.get("/{usuario_id}/emprestimos", response_model=List[EmprestimoResponse], status_code=status.HTTP_200_OK)
def listar_emprestimos_usuario(usuario_id: int, db: Session = Depends(get_db)):
    # Certificar que usuário existe
    services.get_usuario(db, usuario_id)
    return services.get_emprestimos(db, usuario_id=usuario_id)

@router.get("/{usuario_id}/multas", response_model=List[MultaResponse], status_code=status.HTTP_200_OK)
def listar_multas_usuario(usuario_id: int, db: Session = Depends(get_db)):
    # Certificar que usuário existe
    services.get_usuario(db, usuario_id)
    return services.get_multas(db, usuario_id=usuario_id)
