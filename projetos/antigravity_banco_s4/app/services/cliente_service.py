from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.cliente import Cliente
from app.models.enums import CategoriaCliente, SituacaoCliente
from app.schemas.cliente import ClienteCreate, ClienteUpdate
from app.utils.validators import clean_cpf


class ClienteService:
    @staticmethod
    def create_cliente(db: Session, cliente_in: ClienteCreate) -> Cliente:
        cpf_limpo = clean_cpf(cliente_in.cpf)
        
        # Verificar duplicidade de CPF
        if db.query(Cliente).filter(Cliente.cpf == cpf_limpo).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="CPF já cadastrado no sistema.",
            )
        
        # Verificar duplicidade de e-mail
        if db.query(Cliente).filter(Cliente.email == cliente_in.email).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="E-mail já cadastrado no sistema.",
            )
        
        db_cliente = Cliente(
            nome=cliente_in.nome,
            cpf=cpf_limpo,
            email=cliente_in.email,
            categoria=cliente_in.categoria,
            situacao=SituacaoCliente.ATIVO,
        )
        db.add(db_cliente)
        db.commit()
        db.refresh(db_cliente)
        return db_cliente

    @staticmethod
    def get_cliente(db: Session, cliente_id: int) -> Cliente:
        cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
        if not cliente:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cliente com ID {cliente_id} não encontrado.",
            )
        return cliente

    @staticmethod
    def get_clientes(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        categoria: Optional[CategoriaCliente] = None,
        situacao: Optional[SituacaoCliente] = None,
    ) -> List[Cliente]:
        query = db.query(Cliente)
        if categoria:
            query = query.filter(Cliente.categoria == categoria)
        if situacao:
            query = query.filter(Cliente.situacao == situacao)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def update_cliente(db: Session, cliente_id: int, cliente_in: ClienteUpdate) -> Cliente:
        cliente = ClienteService.get_cliente(db, cliente_id)
        
        if cliente_in.email is not None and cliente_in.email != cliente.email:
            email_existente = db.query(Cliente).filter(
                Cliente.email == cliente_in.email,
                Cliente.id != cliente_id,
            ).first()
            if email_existente:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="E-mail já cadastrado para outro cliente.",
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
    def delete_cliente(db: Session, cliente_id: int) -> None:
        cliente = ClienteService.get_cliente(db, cliente_id)
        # Se cliente possui contas que não estão encerradas, bloquear exclusão
        for conta in cliente.contas:
            if conta.estado.value != "encerrada":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Não é possível excluir o cliente pois ele possui a conta {conta.numero} ainda não encerrada.",
                )
        db.delete(cliente)
        db.commit()
