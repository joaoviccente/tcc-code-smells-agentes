from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.enums import CategoriaUsuario, SituacaoUsuario
from app.schemas.usuario import UsuarioCreate, UsuarioResponse, UsuarioUpdate
from app.services import usuario_service

router = APIRouter(prefix="/usuarios", tags=["Usuários"])


@router.post("", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
def criar_usuario(usuario_in: UsuarioCreate, db: Session = Depends(get_db)):
    return usuario_service.create_usuario(db, usuario_in)


@router.get("", response_model=List[UsuarioResponse])
def listar_usuarios(
    categoria: Optional[CategoriaUsuario] = None,
    situacao: Optional[SituacaoUsuario] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    data_referencia: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    return usuario_service.list_usuarios(
        db,
        categoria=categoria,
        situacao=situacao,
        skip=skip,
        limit=limit,
        data_referencia=data_referencia,
    )


@router.get("/{usuario_id}", response_model=UsuarioResponse)
def obter_usuario(
    usuario_id: int,
    data_referencia: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    return usuario_service.get_usuario(db, usuario_id, data_referencia=data_referencia)


@router.put("/{usuario_id}", response_model=UsuarioResponse)
def atualizar_usuario(
    usuario_id: int, usuario_in: UsuarioUpdate, db: Session = Depends(get_db)
):
    return usuario_service.update_usuario(db, usuario_id, usuario_in)


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_usuario(usuario_id: int, db: Session = Depends(get_db)):
    usuario_service.delete_usuario(db, usuario_id)
    return None
