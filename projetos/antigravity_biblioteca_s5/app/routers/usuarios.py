from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.config import CategoriaUsuario, SituacaoUsuario
from app.database import get_db
from app.schemas.usuario import UsuarioCreate, UsuarioResponse, UsuarioUpdate
from app.services import usuario_service

router = APIRouter(prefix="/usuarios", tags=["Usuários"])


@router.post("", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
def criar_usuario(usuario_in: UsuarioCreate, db: Session = Depends(get_db)):
    return usuario_service.criar_usuario(db, usuario_in)


@router.get("", response_model=list[UsuarioResponse])
def listar_usuarios(
    categoria: CategoriaUsuario | None = None,
    situacao: SituacaoUsuario | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return usuario_service.listar_usuarios(
        db,
        categoria=categoria,
        situacao=situacao,
        skip=skip,
        limit=limit,
    )


@router.get("/{usuario_id}", response_model=UsuarioResponse)
def obter_usuario(usuario_id: int, db: Session = Depends(get_db)):
    return usuario_service.obter_usuario_por_id(db, usuario_id)


@router.put("/{usuario_id}", response_model=UsuarioResponse)
def atualizar_usuario(
    usuario_id: int,
    usuario_in: UsuarioUpdate,
    db: Session = Depends(get_db),
):
    return usuario_service.atualizar_usuario(db, usuario_id, usuario_in)


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_usuario(usuario_id: int, db: Session = Depends(get_db)):
    usuario_service.deletar_usuario(db, usuario_id)
    return None
