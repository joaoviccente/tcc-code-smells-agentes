from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import Paginacao, get_db
from ..enums import Categoria, EstadoEmprestimo, EstadoMulta, SituacaoUsuario
from ..models import Emprestimo, Multa, Reserva, Usuario
from ..schemas import EmprestimoSaida, MultaSaida, UsuarioAtualizar, UsuarioCriar, UsuarioSaida
from ..servicos import ErroNegocio, obter

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


def _checar_unicidade(db: Session, dados: dict, ignorar_id: int | None = None) -> None:
    for campo in ("email", "matricula"):
        if campo in dados:
            q = select(Usuario.id).where(getattr(Usuario, campo) == dados[campo])
            if ignorar_id is not None:
                q = q.where(Usuario.id != ignorar_id)
            if db.scalar(q) is not None:
                raise ErroNegocio(f"ja existe usuario com este {campo}")


def _aplicar(usuario: Usuario, dados: dict) -> None:
    nova_situacao = dados.pop("situacao", None)
    for campo, valor in dados.items():
        setattr(usuario, campo, valor)
    if nova_situacao is not None and nova_situacao != usuario.situacao:
        # Reativacao manual encerra a suspensao; suspensao manual e por tempo
        # indeterminado (ate reativacao manual).
        usuario.situacao = nova_situacao
        usuario.suspensao_ate = None


@router.post("", response_model=UsuarioSaida, status_code=status.HTTP_201_CREATED)
def criar(payload: UsuarioCriar, db: Session = Depends(get_db)):
    dados = payload.model_dump()
    dados["email"] = dados["email"].lower()
    _checar_unicidade(db, dados)
    usuario = Usuario(**dados)
    db.add(usuario)
    db.commit()
    return usuario


@router.get("", response_model=list[UsuarioSaida])
def listar(categoria: Categoria | None = None, situacao: SituacaoUsuario | None = None,
           pag: Paginacao = Depends(), db: Session = Depends(get_db)):
    q = select(Usuario).order_by(Usuario.id)
    if categoria:
        q = q.where(Usuario.categoria == categoria)
    if situacao:
        q = q.where(Usuario.situacao == situacao)
    return list(db.scalars(pag.aplicar(q)))


@router.get("/{usuario_id}", response_model=UsuarioSaida)
def detalhar(usuario_id: int, db: Session = Depends(get_db)):
    return obter(db, Usuario, usuario_id, "usuario")


def _atualizar(usuario_id: int, dados: dict, db: Session):
    usuario = obter(db, Usuario, usuario_id, "usuario")
    if "email" in dados and dados["email"] is not None:
        dados["email"] = dados["email"].lower()
    _checar_unicidade(db, dados, ignorar_id=usuario_id)
    _aplicar(usuario, dados)
    db.commit()
    return usuario


@router.put("/{usuario_id}", response_model=UsuarioSaida)
def substituir(usuario_id: int, payload: UsuarioCriar, db: Session = Depends(get_db)):
    return _atualizar(usuario_id, payload.model_dump(), db)


@router.patch("/{usuario_id}", response_model=UsuarioSaida)
def atualizar(usuario_id: int, payload: UsuarioAtualizar, db: Session = Depends(get_db)):
    dados = payload.model_dump(exclude_unset=True)
    nulos = [k for k, v in dados.items() if v is None]
    if nulos:
        raise ErroNegocio(f"campos nao podem ser nulos: {', '.join(nulos)}", 422)
    return _atualizar(usuario_id, dados, db)


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(usuario_id: int, db: Session = Depends(get_db)):
    usuario = obter(db, Usuario, usuario_id, "usuario")
    tem_historico = (
        db.scalar(select(func.count(Emprestimo.id)).where(Emprestimo.usuario_id == usuario_id))
        or db.scalar(select(func.count(Reserva.id)).where(Reserva.usuario_id == usuario_id))
    )
    if tem_historico:
        raise ErroNegocio("usuario possui emprestimos ou reservas registrados e nao pode ser removido; "
                          "considere suspende-lo")
    db.delete(usuario)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{usuario_id}/emprestimos", response_model=list[EmprestimoSaida], tags=["emprestimos"])
def emprestimos_do_usuario(usuario_id: int, estado: EstadoEmprestimo | None = None,
                           pag: Paginacao = Depends(), db: Session = Depends(get_db)):
    obter(db, Usuario, usuario_id, "usuario")
    q = select(Emprestimo).where(Emprestimo.usuario_id == usuario_id).order_by(Emprestimo.data_retirada.desc(),
                                                                               Emprestimo.id.desc())
    if estado:
        q = q.where(Emprestimo.estado == estado)
    return list(db.scalars(pag.aplicar(q)))


@router.get("/{usuario_id}/multas", response_model=list[MultaSaida], tags=["multas"])
def multas_do_usuario(usuario_id: int, estado: EstadoMulta | None = None,
                      pag: Paginacao = Depends(), db: Session = Depends(get_db)):
    obter(db, Usuario, usuario_id, "usuario")
    q = select(Multa).join(Emprestimo).where(Emprestimo.usuario_id == usuario_id).order_by(Multa.id)
    if estado:
        q = q.where(Multa.estado == estado)
    return list(db.scalars(pag.aplicar(q)))
