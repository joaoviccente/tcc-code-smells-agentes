from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.config import DIAS_LIMITE_SUSPENSAO_AUTOMATICA, FATOR_DURACAO_SUSPENSAO
from app.models import Usuario, Emprestimo, Multa
from app.models.enums import CategoriaUsuario, SituacaoUsuario, EstadoEmprestimo, EstadoMulta
from app.schemas.usuario import UsuarioCreate, UsuarioUpdate
from app.utils import get_utcnow


def verificar_e_atualizar_situacao(db: Session, usuario: Usuario, now: Optional[datetime] = None) -> Usuario:
    if now is None:
        now = get_utcnow()

    # 1. Verificar se o usuário possui empréstimos ativos com atraso > 15 dias
    emprestimos_ativos = db.query(Emprestimo).filter(
        Emprestimo.usuario_id == usuario.id,
        Emprestimo.data_devolucao.is_(None)
    ).all()

    maior_atraso = 0
    for emp in emprestimos_ativos:
        if now > emp.data_prevista:
            emp.estado = EstadoEmprestimo.ATRASADO
            dias_atraso = (now.date() - emp.data_prevista.date()).days
            if dias_atraso > maior_atraso:
                maior_atraso = dias_atraso

    if maior_atraso > DIAS_LIMITE_SUSPENSAO_AUTOMATICA:
        usuario.situacao = SituacaoUsuario.SUSPENSO
        fim_calculado = now + timedelta(days=maior_atraso * FATOR_DURACAO_SUSPENSAO)
        if usuario.data_suspensao_fim is None or fim_calculado > usuario.data_suspensao_fim:
            usuario.data_suspensao_fim = fim_calculado
    elif usuario.situacao == SituacaoUsuario.SUSPENSO and usuario.data_suspensao_fim is not None:
        # Se a suspensão expirou e não há empréstimos com atraso > 15 dias
        if now >= usuario.data_suspensao_fim:
            usuario.situacao = SituacaoUsuario.ATIVO
            usuario.data_suspensao_fim = None

    db.commit()
    db.refresh(usuario)
    return usuario


def create_usuario(db: Session, usuario_in: UsuarioCreate) -> Usuario:
    if db.query(Usuario).filter(Usuario.email == usuario_in.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"E-mail '{usuario_in.email}' já está em uso."
        )
    if db.query(Usuario).filter(Usuario.matricula == usuario_in.matricula).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Matrícula '{usuario_in.matricula}' já cadastrada."
        )

    db_usuario = Usuario(
        nome=usuario_in.nome.strip(),
        email=usuario_in.email.strip().lower(),
        matricula=usuario_in.matricula.strip(),
        categoria=usuario_in.categoria,
        situacao=usuario_in.situacao or SituacaoUsuario.ATIVO,
    )
    db.add(db_usuario)
    db.commit()
    db.refresh(db_usuario)
    return db_usuario


def get_usuario_by_id(db: Session, usuario_id: int) -> Usuario:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {usuario_id} não encontrado."
        )
    return verificar_e_atualizar_situacao(db, usuario)


def get_usuarios(
    db: Session,
    categoria: Optional[CategoriaUsuario] = None,
    situacao: Optional[SituacaoUsuario] = None,
    skip: int = 0,
    limit: int = 100
) -> List[Usuario]:
    query = db.query(Usuario)
    if categoria:
        query = query.filter(Usuario.categoria == categoria)
    if situacao:
        query = query.filter(Usuario.situacao == situacao)
    usuarios = query.offset(skip).limit(limit).all()
    now = get_utcnow()
    for u in usuarios:
        verificar_e_atualizar_situacao(db, u, now=now)
    return usuarios


def update_usuario(db: Session, usuario_id: int, usuario_in: UsuarioUpdate) -> Usuario:
    usuario = get_usuario_by_id(db, usuario_id)

    if usuario_in.email is not None and usuario_in.email.strip().lower() != usuario.email:
        email_novo = usuario_in.email.strip().lower()
        if db.query(Usuario).filter(Usuario.email == email_novo, Usuario.id != usuario_id).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"E-mail '{email_novo}' já está em uso."
            )
        usuario.email = email_novo

    if usuario_in.matricula is not None and usuario_in.matricula.strip() != usuario.matricula:
        matricula_nova = usuario_in.matricula.strip()
        if db.query(Usuario).filter(Usuario.matricula == matricula_nova, Usuario.id != usuario_id).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Matrícula '{matricula_nova}' já cadastrada."
            )
        usuario.matricula = matricula_nova

    if usuario_in.nome is not None:
        usuario.nome = usuario_in.nome.strip()
    if usuario_in.categoria is not None:
        usuario.categoria = usuario_in.categoria
    if usuario_in.situacao is not None:
        usuario.situacao = usuario_in.situacao

    db.commit()
    db.refresh(usuario)
    return usuario


def delete_usuario(db: Session, usuario_id: int) -> None:
    usuario = get_usuario_by_id(db, usuario_id)

    # Verificar se o usuário possui empréstimos ativos
    emprestimos_ativos = db.query(Emprestimo).filter(
        Emprestimo.usuario_id == usuario_id,
        Emprestimo.data_devolucao.is_(None)
    ).count()
    if emprestimos_ativos > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir usuário com empréstimos ativos."
        )

    # Verificar se há multas em aberto
    multas_abertas = db.query(Multa).join(Emprestimo).filter(
        Emprestimo.usuario_id == usuario_id,
        Multa.estado == EstadoMulta.ABERTA
    ).count()
    if multas_abertas > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir usuário com multas em aberto."
        )

    db.delete(usuario)
    db.commit()
