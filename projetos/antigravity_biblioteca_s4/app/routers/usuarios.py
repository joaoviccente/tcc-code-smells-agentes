from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.enums import CategoriaUsuario, SituacaoUsuario
from app.schemas.usuario import UsuarioCreate, UsuarioUpdate, UsuarioResponse
from app.schemas.emprestimo import EmprestimoResponse
from app.schemas.multa import MultaResponse
from app.services import usuario_service, emprestimo_service, multa_service

router = APIRouter(prefix="/usuarios", tags=["Usuários"])


@router.post("", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
def criar_usuario(usuario_in: UsuarioCreate, db: Session = Depends(get_db)):
    return usuario_service.create_usuario(db, usuario_in)


@router.get("", response_model=List[UsuarioResponse], status_code=status.HTTP_200_OK)
def listar_usuarios(
    categoria: Optional[CategoriaUsuario] = None,
    situacao: Optional[SituacaoUsuario] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return usuario_service.get_usuarios(db, categoria=categoria, situacao=situacao, skip=skip, limit=limit)


@router.get("/{id}", response_model=UsuarioResponse, status_code=status.HTTP_200_OK)
def obter_usuario(id: int, db: Session = Depends(get_db)):
    return usuario_service.get_usuario_by_id(db, id)


@router.put("/{id}", response_model=UsuarioResponse, status_code=status.HTTP_200_OK)
def atualizar_usuario(id: int, usuario_in: UsuarioUpdate, db: Session = Depends(get_db)):
    return usuario_service.update_usuario(db, id, usuario_in)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_usuario(id: int, db: Session = Depends(get_db)):
    usuario_service.delete_usuario(db, id)
    return None


@router.get("/{id}/emprestimos", response_model=List[EmprestimoResponse], status_code=status.HTTP_200_OK)
def listar_emprestimos_do_usuario(id: int, db: Session = Depends(get_db)):
    # Verifica se usuário existe
    usuario_service.get_usuario_by_id(db, id)
    return emprestimo_service.get_emprestimos(db, usuario_id=id)


@router.get("/{id}/multas", response_model=List[MultaResponse], status_code=status.HTTP_200_OK)
def listar_multas_do_usuario(id: int, db: Session = Depends(get_db)):
    return multa_service.get_multas_por_usuario(db, id)
