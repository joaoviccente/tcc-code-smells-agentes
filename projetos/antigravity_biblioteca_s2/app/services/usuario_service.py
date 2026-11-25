from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.emprestimo import Emprestimo
from app.models.enums import CategoriaUsuario, EstadoEmprestimo, SituacaoUsuario
from app.models.usuario import Usuario
from app.schemas.usuario import UsuarioCreate, UsuarioUpdate
from app.services.regras import DIAS_ATRASO_SUSPENSAO, FATOR_SUSPENSAO


def calcular_dias_atraso(data_fim: datetime, data_prevista: datetime) -> int:
    if data_fim.date() > data_prevista.date():
        return (data_fim.date() - data_prevista.date()).days
    if data_fim > data_prevista:
        return 1
    return 0


def atualizar_situacao_usuario(
    db: Session, usuario: Usuario, data_referencia: Optional[datetime] = None
) -> Usuario:
    if data_referencia is None:
        data_referencia = datetime.now(timezone.utc)
    elif data_referencia.tzinfo is None:
        data_referencia = data_referencia.replace(tzinfo=timezone.utc)

    # 1. Verificar se há algum empréstimo ativo com atraso > 15 dias
    emprestimos_ativos = (
        db.query(Emprestimo)
        .filter(
            Emprestimo.usuario_id == usuario.id,
            Emprestimo.estado.in_([EstadoEmprestimo.ATIVO, EstadoEmprestimo.ATRASADO]),
        )
        .all()
    )

    maior_atraso_dias = 0
    for emp in emprestimos_ativos:
        prevista = (
            emp.data_prevista
            if emp.data_prevista.tzinfo
            else emp.data_prevista.replace(tzinfo=timezone.utc)
        )
        atraso = calcular_dias_atraso(data_referencia, prevista)
        if atraso > 0 and emp.estado != EstadoEmprestimo.ATRASADO:
            emp.estado = EstadoEmprestimo.ATRASADO
        if atraso > maior_atraso_dias:
            maior_atraso_dias = atraso

    # Regra 2: Usuário com atraso superior a 15 dias é automaticamente suspenso
    if maior_atraso_dias > DIAS_ATRASO_SUSPENSAO:
        usuario.situacao = SituacaoUsuario.SUSPENSO
        from datetime import timedelta

        dias_suspensao = FATOR_SUSPENSAO * maior_atraso_dias
        fim_calculado = data_referencia + timedelta(days=dias_suspensao)
        if not usuario.data_fim_suspensao or fim_calculado > (
            usuario.data_fim_suspensao
            if usuario.data_fim_suspensao.tzinfo
            else usuario.data_fim_suspensao.replace(tzinfo=timezone.utc)
        ):
            usuario.data_fim_suspensao = fim_calculado
        db.commit()
        db.refresh(usuario)
        return usuario

    # Se estiver suspenso e o prazo de suspensão já tiver expirado (e não houver empréstimo com atraso > 15 dias)
    if usuario.situacao == SituacaoUsuario.SUSPENSO and usuario.data_fim_suspensao:
        fim_suspensao = (
            usuario.data_fim_suspensao
            if usuario.data_fim_suspensao.tzinfo
            else usuario.data_fim_suspensao.replace(tzinfo=timezone.utc)
        )
        if data_referencia >= fim_suspensao and maior_atraso_dias <= DIAS_ATRASO_SUSPENSAO:
            usuario.situacao = SituacaoUsuario.ATIVO
            usuario.data_fim_suspensao = None
            db.commit()
            db.refresh(usuario)

    return usuario


def create_usuario(db: Session, usuario_in: UsuarioCreate) -> Usuario:
    if db.query(Usuario).filter(Usuario.email == usuario_in.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um usuário cadastrado com este e-mail.",
        )
    if db.query(Usuario).filter(Usuario.matricula == usuario_in.matricula).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um usuário cadastrado com esta matrícula.",
        )

    usuario = Usuario(
        nome=usuario_in.nome,
        email=usuario_in.email,
        matricula=usuario_in.matricula,
        categoria=usuario_in.categoria,
        situacao=SituacaoUsuario.ATIVO,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def get_usuario(
    db: Session, usuario_id: int, data_referencia: Optional[datetime] = None
) -> Usuario:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {usuario_id} não encontrado.",
        )
    return atualizar_situacao_usuario(db, usuario, data_referencia)


def list_usuarios(
    db: Session,
    categoria: Optional[CategoriaUsuario] = None,
    situacao: Optional[SituacaoUsuario] = None,
    skip: int = 0,
    limit: int = 100,
    data_referencia: Optional[datetime] = None,
) -> List[Usuario]:
    query = db.query(Usuario)
    if categoria:
        query = query.filter(Usuario.categoria == categoria)
    if situacao:
        query = query.filter(Usuario.situacao == situacao)
    usuarios = query.offset(skip).limit(limit).all()
    for u in usuarios:
        atualizar_situacao_usuario(db, u, data_referencia)
    return usuarios


def update_usuario(db: Session, usuario_id: int, usuario_in: UsuarioUpdate) -> Usuario:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {usuario_id} não encontrado.",
        )

    if usuario_in.email and usuario_in.email != usuario.email:
        if db.query(Usuario).filter(Usuario.email == usuario_in.email).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um usuário cadastrado com este e-mail.",
            )
        usuario.email = usuario_in.email

    if usuario_in.matricula and usuario_in.matricula != usuario.matricula:
        if db.query(Usuario).filter(Usuario.matricula == usuario_in.matricula).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um usuário cadastrado com esta matrícula.",
            )
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
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {usuario_id} não encontrado.",
        )

    # Não permitir exclusão se houver empréstimo ativo ou atrasado
    tem_emprestimo_ativo = (
        db.query(Emprestimo)
        .filter(
            Emprestimo.usuario_id == usuario_id,
            Emprestimo.estado.in_([EstadoEmprestimo.ATIVO, EstadoEmprestimo.ATRASADO]),
        )
        .first()
    )
    if tem_emprestimo_ativo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir usuário com empréstimos ativos.",
        )

    db.delete(usuario)
    db.commit()
