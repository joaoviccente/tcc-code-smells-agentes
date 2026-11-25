from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.cliente import Cliente
from app.schemas.cliente import ClienteCreate, ClienteUpdate
from app.config import CategoriaCliente, SituacaoCliente


def criar_cliente(db: Session, cliente_in: ClienteCreate) -> Cliente:
    # Verifica unicidade do CPF
    if db.query(Cliente).filter(Cliente.cpf == cliente_in.cpf).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe um cliente cadastrado com o CPF {cliente_in.cpf}."
        )
    # Verifica unicidade do E-mail
    if db.query(Cliente).filter(Cliente.email == cliente_in.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe um cliente cadastrado com o e-mail {cliente_in.email}."
        )

    db_cliente = Cliente(
        nome=cliente_in.nome,
        cpf=cliente_in.cpf,
        email=cliente_in.email,
        categoria=cliente_in.categoria,
        situacao=cliente_in.situacao,
    )
    db.add(db_cliente)
    db.commit()
    db.refresh(db_cliente)
    return db_cliente


def listar_clientes(
    db: Session,
    categoria: Optional[CategoriaCliente] = None,
    situacao: Optional[SituacaoCliente] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Cliente]:
    query = db.query(Cliente)
    if categoria:
        query = query.filter(Cliente.categoria == categoria)
    if situacao:
        query = query.filter(Cliente.situacao == situacao)
    return query.offset(skip).limit(limit).all()


def obter_cliente_por_id(db: Session, cliente_id: int) -> Cliente:
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cliente com ID {cliente_id} não encontrado."
        )
    return cliente


def atualizar_cliente(db: Session, cliente_id: int, cliente_in: ClienteUpdate) -> Cliente:
    cliente = obter_cliente_por_id(db, cliente_id)

    if cliente_in.email and cliente_in.email != cliente.email:
        existente = db.query(Cliente).filter(Cliente.email == cliente_in.email).first()
        if existente:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Já existe um cliente cadastrado com o e-mail {cliente_in.email}."
            )
        cliente.email = cliente_in.email

    if cliente_in.nome is not None:
        cliente.nome = cliente_in.nome
    if cliente_in.categoria is not None:
        cliente.categoria = cliente_in.categoria
    if cliente_in.situacao is not None:
        cliente.situacao = cliente_in.situacao

    db.commit()
    db.refresh(cliente)
    return cliente


def deletar_cliente(db: Session, cliente_id: int) -> None:
    cliente = obter_cliente_por_id(db, cliente_id)
    # Verifica se tem contas ativas com saldo
    for conta in cliente.contas:
        if conta.saldo != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Não é possível excluir o cliente. A conta {conta.numero} possui saldo de R$ {conta.saldo}."
            )
    db.delete(cliente)
    db.commit()
