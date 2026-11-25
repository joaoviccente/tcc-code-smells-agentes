from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import garantir_unico, get_db
from app.enums import Categoria, SituacaoUsuario
from app.erros import ErroNegocio
from app.models import Emprestimo, Multa, Reserva, Usuario
from app.schemas import (
    EmprestimoSaida,
    MultaSaida,
    ReservaSaida,
    UsuarioAtualizar,
    UsuarioCriar,
    UsuarioSaida,
)
from app.servicos import obter

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.post("", response_model=UsuarioSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: UsuarioCriar, db: Session = Depends(get_db)):
    garantir_unico(db, Usuario, "email", dados.email)
    garantir_unico(db, Usuario, "matricula", dados.matricula)
    usuario = Usuario(**dados.model_dump())
    db.add(usuario)
    db.commit()
    return usuario


@router.get("", response_model=list[UsuarioSaida])
def listar(categoria: Categoria | None = None, situacao: SituacaoUsuario | None = None,
           offset: int = Query(0, ge=0), limite: int = Query(100, ge=1, le=500),
           db: Session = Depends(get_db)):
    q = select(Usuario).order_by(Usuario.id)
    if categoria:
        q = q.where(Usuario.categoria == categoria)
    if situacao:
        q = q.where(Usuario.situacao == situacao)
    return db.scalars(q.offset(offset).limit(limite)).all()


@router.get("/{usuario_id}", response_model=UsuarioSaida)
def detalhar(usuario_id: int, db: Session = Depends(get_db)):
    return obter(db, Usuario, usuario_id, "Usuario")


@router.api_route("/{usuario_id}", methods=["PUT", "PATCH"], response_model=UsuarioSaida)
def atualizar(usuario_id: int, dados: UsuarioAtualizar, db: Session = Depends(get_db)):
    usuario: Usuario = obter(db, Usuario, usuario_id, "Usuario")
    campos = dados.model_dump(exclude_unset=True)
    if campos.get("email") is not None:
        garantir_unico(db, Usuario, "email", campos["email"], usuario.id)
    if campos.get("matricula") is not None:
        garantir_unico(db, Usuario, "matricula", campos["matricula"], usuario.id)
    for campo, valor in campos.items():
        if valor is None:
            raise ErroNegocio(f"Campo '{campo}' nao pode ser nulo", status.HTTP_422_UNPROCESSABLE_CONTENT)
        setattr(usuario, campo, valor)
    if "situacao" in campos:
        # Alteracao manual da situacao encerra/define suspensao por prazo indeterminado
        usuario.suspenso_ate = None
    db.commit()
    return usuario


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(usuario_id: int, db: Session = Depends(get_db)):
    usuario: Usuario = obter(db, Usuario, usuario_id, "Usuario")
    if usuario.emprestimos or usuario.reservas:
        raise ErroNegocio("Usuario possui historico de emprestimos/reservas e nao pode ser removido")
    db.delete(usuario)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{usuario_id}/emprestimos", response_model=list[EmprestimoSaida], tags=["Emprestimos"])
def emprestimos_do_usuario(usuario_id: int, db: Session = Depends(get_db)):
    obter(db, Usuario, usuario_id, "Usuario")
    return db.scalars(select(Emprestimo).where(Emprestimo.usuario_id == usuario_id)
                      .order_by(Emprestimo.data_retirada.desc(), Emprestimo.id.desc())).all()


@router.get("/{usuario_id}/multas", response_model=list[MultaSaida], tags=["Multas"])
def multas_do_usuario(usuario_id: int, db: Session = Depends(get_db)):
    obter(db, Usuario, usuario_id, "Usuario")
    return db.scalars(select(Multa).join(Emprestimo).where(Emprestimo.usuario_id == usuario_id)
                      .order_by(Multa.id)).all()


@router.get("/{usuario_id}/reservas", response_model=list[ReservaSaida], tags=["Reservas"])
def reservas_do_usuario(usuario_id: int, db: Session = Depends(get_db)):
    obter(db, Usuario, usuario_id, "Usuario")
    return db.scalars(select(Reserva).where(Reserva.usuario_id == usuario_id).order_by(Reserva.id)).all()
