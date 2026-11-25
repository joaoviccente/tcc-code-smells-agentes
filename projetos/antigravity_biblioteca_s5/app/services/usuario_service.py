from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import CategoriaUsuario, EstadoEmprestimo, EstadoMulta, SituacaoUsuario
from app.models.emprestimo import Emprestimo
from app.models.multa import Multa
from app.models.usuario import Usuario
from app.schemas.usuario import UsuarioCreate, UsuarioUpdate


def verificar_e_atualizar_situacao(db: Session, usuario: Usuario, now: datetime | None = None) -> Usuario:
    if now is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 1. Se suspenso e o prazo da suspensão expirou, reativa
    if usuario.situacao == SituacaoUsuario.SUSPENSO:
        if usuario.suspenso_ate and usuario.suspenso_ate <= now:
            usuario.situacao = SituacaoUsuario.ATIVO
            usuario.suspenso_ate = None
            db.commit()
            db.refresh(usuario)

    # 2. Regra 2: Verifica se possui qualquer empréstimo com atraso superior a 15 dias
    emprestimos_atrasados = (
        db.query(Emprestimo)
        .filter(
            Emprestimo.usuario_id == usuario.id,
            Emprestimo.data_devolucao.is_(None),
            Emprestimo.data_prevista < now,
        )
        .all()
    )

    maior_atraso_dias = 0
    for emp in emprestimos_atrasados:
        emp.estado = EstadoEmprestimo.ATRASADO
        dias = (now.date() - emp.data_prevista.date()).days
        if dias > maior_atraso_dias:
            maior_atraso_dias = dias

    if maior_atraso_dias > 15:
        from datetime import timedelta

        usuario.situacao = SituacaoUsuario.SUSPENSO
        nova_suspensao = now + timedelta(days=2 * maior_atraso_dias)
        if usuario.suspenso_ate is None or nova_suspensao > usuario.suspenso_ate:
            usuario.suspenso_ate = nova_suspensao
        db.commit()
        db.refresh(usuario)

    return usuario


def criar_usuario(db: Session, usuario_in: UsuarioCreate) -> Usuario:
    if db.query(Usuario).filter(Usuario.email == usuario_in.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"E-mail '{usuario_in.email}' já cadastrado.",
        )
    if db.query(Usuario).filter(Usuario.matricula == usuario_in.matricula).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Matrícula '{usuario_in.matricula}' já cadastrada.",
        )

    usuario = Usuario(
        nome=usuario_in.nome,
        email=usuario_in.email,
        matricula=usuario_in.matricula,
        categoria=usuario_in.categoria,
        situacao=usuario_in.situacao,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def listar_usuarios(
    db: Session,
    categoria: CategoriaUsuario | None = None,
    situacao: SituacaoUsuario | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Usuario]:
    query = db.query(Usuario)
    if categoria:
        query = query.filter(Usuario.categoria == categoria)
    if situacao:
        query = query.filter(Usuario.situacao == situacao)
    usuarios = query.offset(skip).limit(limit).all()
    for u in usuarios:
        verificar_e_atualizar_situacao(db, u)
    return usuarios


def obter_usuario_por_id(db: Session, usuario_id: int) -> Usuario:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário com ID {usuario_id} não encontrado.",
        )
    return verificar_e_atualizar_situacao(db, usuario)


def atualizar_usuario(db: Session, usuario_id: int, usuario_in: UsuarioUpdate) -> Usuario:
    usuario = obter_usuario_por_id(db, usuario_id)

    if usuario_in.email and usuario_in.email != usuario.email:
        if db.query(Usuario).filter(Usuario.email == usuario_in.email).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"E-mail '{usuario_in.email}' já cadastrado.",
            )
        usuario.email = usuario_in.email

    if usuario_in.matricula and usuario_in.matricula != usuario.matricula:
        if db.query(Usuario).filter(Usuario.matricula == usuario_in.matricula).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Matrícula '{usuario_in.matricula}' já cadastrada.",
            )
        usuario.matricula = usuario_in.matricula

    if usuario_in.nome is not None:
        usuario.nome = usuario_in.nome
    if usuario_in.categoria is not None:
        usuario.categoria = usuario_in.categoria
    if usuario_in.situacao is not None:
        usuario.situacao = usuario_in.situacao
    if usuario_in.suspenso_ate is not None:
        usuario.suspenso_ate = usuario_in.suspenso_ate

    db.commit()
    db.refresh(usuario)
    return usuario


def deletar_usuario(db: Session, usuario_id: int) -> None:
    usuario = obter_usuario_por_id(db, usuario_id)

    # Verifica se possui empréstimos ativos ou atrasados
    emprestimos_ativos = (
        db.query(Emprestimo)
        .filter(
            Emprestimo.usuario_id == usuario_id,
            Emprestimo.data_devolucao.is_(None),
        )
        .count()
    )
    if emprestimos_ativos > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir usuário com empréstimos em andamento.",
        )

    # Verifica se possui multas abertas
    multas_abertas = (
        db.query(Multa)
        .join(Emprestimo)
        .filter(
            Emprestimo.usuario_id == usuario_id,
            Multa.estado == EstadoMulta.ABERTA,
        )
        .count()
    )
    if multas_abertas > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir usuário com multas em aberto.",
        )

    db.delete(usuario)
    db.commit()
