from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.cliente import Cliente, SituacaoCliente
from app.schemas.cliente import ClienteCreate, ClienteUpdate


class ClienteService:
    @staticmethod
    def criar_cliente(db: Session, cliente_in: ClienteCreate) -> Cliente:
        # Verifica duplicidade de CPF
        if db.query(Cliente).filter(Cliente.cpf == cliente_in.cpf).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Já existe um cliente cadastrado com o CPF {cliente_in.cpf}.",
            )
        
        # Verifica duplicidade de e-mail
        if db.query(Cliente).filter(Cliente.email == cliente_in.email).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Já existe um cliente cadastrado com o e-mail {cliente_in.email}.",
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

    @staticmethod
    def obter_cliente(db: Session, cliente_id: int) -> Cliente:
        cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
        if not cliente:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cliente #{cliente_id} não encontrado.",
            )
        return cliente

    @staticmethod
    def listar_clientes(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        categoria: Optional[str] = None,
        situacao: Optional[str] = None,
    ) -> List[Cliente]:
        query = db.query(Cliente)
        if categoria:
            query = query.filter(Cliente.categoria == categoria)
        if situacao:
            query = query.filter(Cliente.situacao == situacao)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def atualizar_cliente(db: Session, cliente_id: int, cliente_in: ClienteUpdate) -> Cliente:
        cliente = ClienteService.obter_cliente(db, cliente_id)
        
        if cliente_in.email and cliente_in.email != cliente.email:
            if db.query(Cliente).filter(Cliente.email == cliente_in.email, Cliente.id != cliente_id).first():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Já existe um cliente cadastrado com o e-mail {cliente_in.email}.",
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

    @staticmethod
    def deletar_cliente(db: Session, cliente_id: int) -> None:
        cliente = ClienteService.obter_cliente(db, cliente_id)
        # Verifica se há contas com saldo não nulo
        for conta in cliente.contas:
            if conta.saldo != 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Não é possível excluir cliente com conta #{conta.numero} possuindo saldo diferente de zero (R$ {conta.saldo}).",
                )
        db.delete(cliente)
        db.commit()
