from sqlalchemy import Column, Integer, String, Enum as SQLEnum, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from app.config import CategoriaCliente, SituacaoCliente, get_current_time


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(150), nullable=False)
    cpf = Column(String(14), unique=True, index=True, nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    categoria = Column(
        SQLEnum(CategoriaCliente, values_callable=lambda x: [e.value for e in x]),
        default=CategoriaCliente.COMUM,
        nullable=False,
    )
    situacao = Column(
        SQLEnum(SituacaoCliente, values_callable=lambda x: [e.value for e in x]),
        default=SituacaoCliente.ATIVO,
        nullable=False,
    )
    created_at = Column(DateTime, default=get_current_time, nullable=False)

    contas = relationship("Conta", back_populates="cliente", cascade="all, delete-orphan")
