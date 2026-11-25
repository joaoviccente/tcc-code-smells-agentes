from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..deps import garantir_unico, get_db
from ..erros import ErroNegocio
from ..models import Emprestimo, Multa, Reserva, Usuario
from ..schemas import (
    Categoria, EmprestimoSaida, MultaSaida, Situacao, UsuarioAtualizar, UsuarioCriar,
    UsuarioSaida,
)
from ..servicos import obter

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.post("", response_model=UsuarioSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: UsuarioCriar, db: Session = Depends(get_db)):
    garantir_unico(db, Usuario, "email", str(dados.email).lower())
    garantir_unico(db, Usuario, "matricula", dados.matricula)
    u = Usuario(**dados.model_dump())
    u.email = u.email.lower()
    if u.situacao == "suspenso":
        u.motivo_suspensao = "manual"
    db.add(u)
    db.commit()
    return u


@router.get("", response_model=list[UsuarioSaida])
def listar(
    categoria: Categoria | None = None,
    situacao: Situacao | None = None,
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


def _atualizar(usuario_id: int, valores: dict, db: Session):
    u = obter(db, Usuario, usuario_id, "Usuario")
    valores = {k: v for k, v in valores.items() if v is not None}
    if "email" in valores:
        valores["email"] = str(valores["email"]).lower()
        garantir_unico(db, Usuario, "email", valores["email"], u.id)
    if "matricula" in valores:
        garantir_unico(db, Usuario, "matricula", valores["matricula"], u.id)
    if "categoria" in valores and valores["categoria"] != u.categoria:
        abertos = db.scalar(select(func.count()).select_from(Emprestimo).where(
            Emprestimo.usuario_id == u.id, Emprestimo.estado.in_(("ativo", "atrasado"))))
        if abertos:
            raise ErroNegocio("Nao e possivel alterar a categoria com emprestimos em aberto",
                              409, "emprestimos_em_aberto")
    nova_situacao = valores.pop("situacao", None)
    for k, v in valores.items():
        setattr(u, k, v)
    if nova_situacao and nova_situacao != u.situacao:
        u.situacao = nova_situacao
        # Alteracao administrativa: suspensao manual ou reativacao (encerra suspensao por atraso).
        u.motivo_suspensao = "manual" if nova_situacao == "suspenso" else None
        u.suspenso_ate = None
    db.commit()
    return u


@router.put("/{usuario_id}", response_model=UsuarioSaida)
def substituir(usuario_id: int, dados: UsuarioCriar, db: Session = Depends(get_db)):
    valores = dados.model_dump()
    if "situacao" not in dados.model_fields_set:
        valores.pop("situacao")  # PUT sem situacao nao altera suspensao vigente
    return _atualizar(usuario_id, valores, db)


@router.patch("/{usuario_id}", response_model=UsuarioSaida)
def atualizar(usuario_id: int, dados: UsuarioAtualizar, db: Session = Depends(get_db)):
    return _atualizar(usuario_id, dados.model_dump(exclude_unset=True), db)


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(usuario_id: int, db: Session = Depends(get_db)):
    u = obter(db, Usuario, usuario_id, "Usuario")
    tem_emp = db.scalar(select(func.count()).select_from(Emprestimo).where(Emprestimo.usuario_id == u.id))
    tem_res = db.scalar(select(func.count()).select_from(Reserva).where(Reserva.usuario_id == u.id))
    if tem_emp or tem_res:
        raise ErroNegocio("Usuario possui historico de emprestimos/reservas e nao pode ser removido",
                          409, "possui_historico")
    db.delete(u)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{usuario_id}/emprestimos", response_model=list[EmprestimoSaida])
def emprestimos_do_usuario(
    usuario_id: int,
    estado: str | None = Query(None, pattern="^(ativo|devolvido|atrasado)$"),
    db: Session = Depends(get_db),
):
    obter(db, Usuario, usuario_id, "Usuario")
    q = (select(Emprestimo).options(selectinload(Emprestimo.multa))
         .where(Emprestimo.usuario_id == usuario_id).order_by(Emprestimo.data_retirada.desc(), Emprestimo.id.desc()))
    if estado:
        q = q.where(Emprestimo.estado == estado)
    return db.scalars(q).all()


@router.get("/{usuario_id}/multas", response_model=list[MultaSaida])
def multas_do_usuario(
    usuario_id: int,
    estado: str | None = Query(None, pattern="^(aberta|paga|perdoada)$"),
    db: Session = Depends(get_db),
):
    obter(db, Usuario, usuario_id, "Usuario")
    q = (select(Multa).join(Emprestimo).where(Emprestimo.usuario_id == usuario_id)
         .order_by(Multa.data_geracao.desc(), Multa.id.desc()))
    if estado:
        q = q.where(Multa.estado == estado)
    return db.scalars(q).all()

