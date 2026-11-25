from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..apresentacao import emprestimo_saida
from ..deps import get_db
from ..models import Emprestimo, Multa, Reserva, Usuario
from ..schemas import EmprestimoSaida, MultaSaida, UsuarioAtualizar, UsuarioCriar, UsuarioSaida
from ..servicos import conflito, obter

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


def _verificar_unicidade(db: Session, email: str | None, matricula: str | None, ignorar_id: int | None = None):
    for campo, valor in (("email", email), ("matricula", matricula)):
        if valor is None:
            continue
        q = select(Usuario.id).where(func.lower(getattr(Usuario, campo)) == valor.lower())
        if ignorar_id is not None:
            q = q.where(Usuario.id != ignorar_id)
        if db.scalar(q) is not None:
            raise conflito(f"{campo.upper()}_DUPLICADO", f"Ja existe usuario com este {campo}")


def _aplicar_situacao(usuario: Usuario, situacao: str) -> None:
    """Alteracao manual de situacao: anula os dados da suspensao automatica."""
    usuario.situacao = situacao
    usuario.suspensao_automatica = False
    usuario.suspenso_ate = None


@router.post("", response_model=UsuarioSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: UsuarioCriar, db: Session = Depends(get_db)):
    _verificar_unicidade(db, dados.email, dados.matricula)
    usuario = Usuario(**dados.model_dump(exclude={"situacao"}), suspensao_automatica=False)
    _aplicar_situacao(usuario, dados.situacao)
    db.add(usuario)
    db.commit()
    return usuario


@router.get("", response_model=list[UsuarioSaida])
def listar(
    categoria: Literal["aluno", "professor", "visitante"] | None = None,
    situacao: Literal["ativo", "suspenso"] | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = select(Usuario).order_by(Usuario.id)
    if categoria:
        q = q.where(Usuario.categoria == categoria)
    if situacao:
        q = q.where(Usuario.situacao == situacao)
    return db.scalars(q.offset(skip).limit(limit)).all()


@router.get("/{usuario_id}", response_model=UsuarioSaida)
def detalhar(usuario_id: int, db: Session = Depends(get_db)):
    return obter(db, Usuario, usuario_id, "Usuario")


def _atualizar(usuario_id: int, dados: UsuarioAtualizar | UsuarioCriar, db: Session, parcial: bool):
    usuario = obter(db, Usuario, usuario_id, "Usuario")
    valores = dados.model_dump(exclude_unset=parcial)
    _verificar_unicidade(db, valores.get("email"), valores.get("matricula"), ignorar_id=usuario.id)
    situacao = valores.pop("situacao", None)
    for k, v in valores.items():
        if v is not None:
            setattr(usuario, k, v)
    if situacao is not None and situacao != usuario.situacao:
        _aplicar_situacao(usuario, situacao)
    db.commit()
    return usuario


@router.put("/{usuario_id}", response_model=UsuarioSaida)
def substituir(usuario_id: int, dados: UsuarioCriar, db: Session = Depends(get_db)):
    return _atualizar(usuario_id, dados, db, parcial=False)


@router.patch("/{usuario_id}", response_model=UsuarioSaida)
def atualizar(usuario_id: int, dados: UsuarioAtualizar, db: Session = Depends(get_db)):
    return _atualizar(usuario_id, dados, db, parcial=True)


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(usuario_id: int, db: Session = Depends(get_db)):
    usuario = obter(db, Usuario, usuario_id, "Usuario")
    tem_historico = db.scalar(
        select(func.count()).select_from(Emprestimo).where(Emprestimo.usuario_id == usuario.id)
    ) or db.scalar(select(func.count()).select_from(Reserva).where(Reserva.usuario_id == usuario.id))
    if tem_historico:
        raise conflito("USUARIO_COM_HISTORICO", "Usuario possui emprestimos ou reservas e nao pode ser removido")
    db.delete(usuario)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{usuario_id}/emprestimos", response_model=list[EmprestimoSaida])
def emprestimos_do_usuario(
    usuario_id: int,
    estado: Literal["ativo", "devolvido", "atrasado"] | None = None,
    db: Session = Depends(get_db),
):
    obter(db, Usuario, usuario_id, "Usuario")
    q = select(Emprestimo).where(Emprestimo.usuario_id == usuario_id).order_by(Emprestimo.data_retirada.desc(), Emprestimo.id.desc())
    if estado:
        q = q.where(Emprestimo.estado == estado)
    return [emprestimo_saida(e) for e in db.scalars(q)]


@router.get("/{usuario_id}/multas", response_model=list[MultaSaida])
def multas_do_usuario(
    usuario_id: int,
    estado: Literal["aberta", "paga", "perdoada"] | None = None,
    db: Session = Depends(get_db),
):
    obter(db, Usuario, usuario_id, "Usuario")
    q = select(Multa).join(Emprestimo).where(Emprestimo.usuario_id == usuario_id).order_by(Multa.id)
    if estado:
        q = q.where(Multa.estado == estado)
    return db.scalars(q).all()
