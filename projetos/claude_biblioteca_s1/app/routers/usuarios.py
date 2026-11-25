from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import servicos
from app.deps import get_db
from app.models import (Categoria, Emprestimo, EstadoEmprestimo, EstadoMulta, EstadoReserva, Multa, Reserva,
                        SituacaoUsuario, Usuario)
from app.schemas import (EmprestimoSaida, MultaSaida, ReservaSaida, UsuarioAtualizar, UsuarioCriar,
                         UsuarioSaida)

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.post("", response_model=UsuarioSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: UsuarioCriar, db: Session = Depends(get_db)):
    return servicos.salvar_usuario(db, dados.model_dump())


@router.get("", response_model=list[UsuarioSaida])
def listar(categoria: Categoria | None = None, situacao: SituacaoUsuario | None = None,
           offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    q = select(Usuario).order_by(Usuario.id)
    if categoria:
        q = q.where(Usuario.categoria == categoria)
    if situacao:
        q = q.where(Usuario.situacao == situacao)
    return db.scalars(q.offset(offset).limit(limit)).all()


@router.get("/{usuario_id}", response_model=UsuarioSaida)
def detalhar(usuario_id: int, db: Session = Depends(get_db)):
    return servicos.obter(db, Usuario, usuario_id, "Usuario")


@router.put("/{usuario_id}", response_model=UsuarioSaida)
def substituir(usuario_id: int, dados: UsuarioCriar, db: Session = Depends(get_db)):
    usuario = servicos.obter(db, Usuario, usuario_id, "Usuario")
    return servicos.salvar_usuario(db, dados.model_dump(), usuario)


@router.patch("/{usuario_id}", response_model=UsuarioSaida)
def atualizar(usuario_id: int, dados: UsuarioAtualizar, db: Session = Depends(get_db)):
    usuario = servicos.obter(db, Usuario, usuario_id, "Usuario")
    return servicos.salvar_usuario(db, dados.model_dump(exclude_unset=True, exclude_none=True), usuario)


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir(usuario_id: int, db: Session = Depends(get_db)):
    servicos.excluir_usuario(db, servicos.obter(db, Usuario, usuario_id, "Usuario"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{usuario_id}/emprestimos", response_model=list[EmprestimoSaida])
def emprestimos_do_usuario(usuario_id: int, estado: EstadoEmprestimo | None = None,
                           db: Session = Depends(get_db)):
    servicos.obter(db, Usuario, usuario_id, "Usuario")
    q = select(Emprestimo).where(Emprestimo.usuario_id == usuario_id).order_by(Emprestimo.id)
    if estado:
        q = q.where(Emprestimo.estado == estado)
    return db.scalars(q).all()


@router.get("/{usuario_id}/multas", response_model=list[MultaSaida])
def multas_do_usuario(usuario_id: int, estado: EstadoMulta | None = None, db: Session = Depends(get_db)):
    servicos.obter(db, Usuario, usuario_id, "Usuario")
    q = select(Multa).join(Emprestimo).where(Emprestimo.usuario_id == usuario_id).order_by(Multa.id)
    if estado:
        q = q.where(Multa.estado == estado)
    return db.scalars(q).all()


@router.get("/{usuario_id}/reservas", response_model=list[ReservaSaida])
def reservas_do_usuario(usuario_id: int, estado: EstadoReserva | None = None, db: Session = Depends(get_db)):
    servicos.obter(db, Usuario, usuario_id, "Usuario")
    q = select(Reserva).where(Reserva.usuario_id == usuario_id).order_by(Reserva.id)
    if estado:
        q = q.where(Reserva.estado == estado)
    return db.scalars(q).all()
