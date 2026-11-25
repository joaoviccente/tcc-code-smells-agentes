from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.cliente import Cliente
from app.schemas.cliente import ClienteCreate, ClienteUpdate
from app.utils.validators import clean_cpf, format_cpf


class ClienteService:
    @staticmethod
    def get_by_id(db: Session, cliente_id: int) -> Cliente:
        cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
        if not cliente:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cliente com ID {cliente_id} não encontrado.",
            )
        return cliente

    @staticmethod
    def get_by_cpf(db: Session, cpf: str) -> Optional[Cliente]:
        formatted_cpf = format_cpf(clean_cpf(cpf))
        return db.query(Cliente).filter(Cliente.cpf == formatted_cpf).first()

    @staticmethod
    def list(db: Session, skip: int = 0, limit: int = 100) -> List[Cliente]:
        return db.query(Cliente).offset(skip).limit(limit).all()

    @staticmethod
    def create(db: Session, cliente_in: ClienteCreate) -> Cliente:
        # Verifica se CPF já está cadastrado
        if ClienteService.get_by_cpf(db, cliente_in.cpf):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"CPF {cliente_in.cpf} já cadastrado para outro cliente.",
            )

        # Verifica se E-mail já está cadastrado
        existing_email = db.query(Cliente).filter(Cliente.email == cliente_in.email).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"E-mail {cliente_in.email} já cadastrado para outro cliente.",
            )

        cliente = Cliente(
            nome=cliente_in.nome,
            cpf=cliente_in.cpf,
            email=cliente_in.email,
            categoria=cliente_in.categoria,
            situacao=cliente_in.situacao,
        )
        db.add(cliente)
        db.commit()
        db.refresh(cliente)
        return cliente

    @staticmethod
    def update(db: Session, cliente_id: int, cliente_in: ClienteUpdate) -> Cliente:
        cliente = ClienteService.get_by_id(db, cliente_id)

        if cliente_in.email and cliente_in.email != cliente.email:
            existing = db.query(Cliente).filter(Cliente.email == cliente_in.email).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"E-mail {cliente_in.email} já cadastrado.",
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
    def delete(db: Session, cliente_id: int) -> None:
        cliente = ClienteService.get_by_id(db, cliente_id)
        # Verifica se tem contas vinculadas
        if cliente.contas:
            for conta in cliente.contas:
                if conta.saldo != 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Não é possível remover cliente com contas que possuem saldo diferente de zero.",
                    )
        db.delete(cliente)
        db.commit()
