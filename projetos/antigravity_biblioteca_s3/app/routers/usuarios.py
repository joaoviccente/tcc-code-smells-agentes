from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.enums import CategoriaUsuario, SituacaoUsuario
from app.schemas.usuario import UsuarioCreate, UsuarioUpdate, UsuarioResponse
from app.services import usuario_service

router = APIRouter(prefix="/usuarios", tags=["Usuários"])


@router.post("", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
def cadastrar_usuario(usuario_in: UsuarioCreate, db: Session = Depends(get_db)):
    """Cadastra um novo usuário na biblioteca."""
    return usuario_service.create_usuario(db, usuario_in)


@router.get("", response_model=List[UsuarioResponse])
def listar_usuarios(
    categoria: Optional[CategoriaUsuario] = Query(None, description="Filtrar por categoria"),
    situacao: Optional[SituacaoUsuario] = Query(None, description="Filtrar por situação"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Lista usuários cadastrados."""
    return usuario_service.get_usuarios(db, categoria=categoria, situacao=situacao, skip=skip, limit=limit)


@router.get("/{id}", response_model=UsuarioResponse)
def obter_usuario(id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de um usuário específico."""
    return usuario_service.get_usuario_by_id(db, id)


@router.put("/{id}", response_model=UsuarioResponse)
def atualizar_usuario(id: int, usuario_in: UsuarioUpdate, db: Session = Depends(get_db)):
    """Atualiza dados cadastrais de um usuário."""
    return usuario_service.update_usuario(db, id, usuario_in)


@router.patch("/{id}", response_model=UsuarioResponse)
def atualizar_usuario_parcial(id: int, usuario_in: UsuarioUpdate, db: Session = Depends(get_db)):
    """Atualiza parcialmente dados de um usuário."""
    return usuario_service.update_usuario(db, id, usuario_in)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_usuario(id: int, db: Session = Depends(get_db)):
    """Remove um usuário do sistema."""
    usuario_service.delete_usuario(db, id)
    return None
