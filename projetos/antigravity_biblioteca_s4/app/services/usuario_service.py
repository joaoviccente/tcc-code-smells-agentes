from datetime import datetime
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.usuario import Usuario
from app.models.enums import SituacaoUsuario, CategoriaUsuario
from app.schemas.usuario import UsuarioCreate, UsuarioUpdate


def check_e_atualizar_suspensao(usuario: Usuario, current_time: Optional[datetime] = None) -> None:
    """Se o usuário estiver suspenso e a data final da suspensão já tiver passado, reativa o usuário."""
    if usuario.situacao == SituacaoUsuario.SUSPENSO and usuario.data_fim_suspensao:
        agora = current_time or datetime.now()
        if agora >= usuario.data_fim_suspensao:
            usuario.situacao = SituacaoUsuario.ATIVO
            usuario.data_fim_suspensao = None


def get_usuarios(
    db: Session,
    categoria: Optional[CategoriaUsuario] = None,
    situacao: Optional[SituacaoUsuario] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Usuario]:
    query = db.query(Usuario)
    if categoria:
        query = query.filter(Usuario.categoria == categoria)
    if situacao:
        query = query.filter(Usuario.situacao == situacao)
    usuarios = query.offset(skip).limit(limit).all()
    for u in usuarios:
        check_e_atualizar_suspensao(u)
    db.commit()
    return usuarios


def get_usuario_by_id(db: Session, usuario_id: int) -> Usuario:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Usuário com ID {usuario_id} não encontrado.")
    check_e_atualizar_suspensao(usuario)
    db.commit()
    return usuario


def create_usuario(db: Session, usuario_in: UsuarioCreate) -> Usuario:
    if db.query(Usuario).filter(Usuario.email == usuario_in.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já existe um usuário cadastrado com este e-mail.")
    if db.query(Usuario).filter(Usuario.matricula == usuario_in.matricula).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já existe um usuário cadastrado com esta matrícula.")

    usuario = Usuario(
        nome=usuario_in.nome,
        email=usuario_in.email,
        matricula=usuario_in.matricula,
        categoria=usuario_in.categoria,
        situacao=usuario_in.situacao or SituacaoUsuario.ATIVO,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def update_usuario(db: Session, usuario_id: int, usuario_in: UsuarioUpdate) -> Usuario:
    usuario = get_usuario_by_id(db, usuario_id)

    if usuario_in.email and usuario_in.email != usuario.email:
        if db.query(Usuario).filter(Usuario.email == usuario_in.email).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já existe um usuário cadastrado com este e-mail.")
        usuario.email = usuario_in.email

    if usuario_in.matricula and usuario_in.matricula != usuario.matricula:
        if db.query(Usuario).filter(Usuario.matricula == usuario_in.matricula).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já existe um usuário cadastrado com esta matrícula.")
        usuario.matricula = usuario_in.matricula

    if usuario_in.nome is not None:
        usuario.nome = usuario_in.nome
    if usuario_in.categoria is not None:
        usuario.categoria = usuario_in.categoria
    if usuario_in.situacao is not None:
        usuario.situacao = usuario_in.situacao
    if usuario_in.data_fim_suspensao is not None:
        usuario.data_fim_suspensao = usuario_in.data_fim_suspensao

    db.commit()
    db.refresh(usuario)
    return usuario


def delete_usuario(db: Session, usuario_id: int) -> None:
    usuario = get_usuario_by_id(db, usuario_id)
    # Verificar se o usuário possui empréstimos ativos
    from app.models.enums import EstadoEmprestimo
    tem_emprestimos_ativos = any(
        emp.estado in (EstadoEmprestimo.ATIVO, EstadoEmprestimo.ATRASADO)
        for emp in usuario.emprestimos
    )
    if tem_emprestimos_ativos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir usuário com empréstimos em andamento.",
        )
    db.delete(usuario)
    db.commit()
