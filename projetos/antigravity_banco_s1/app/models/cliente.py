import enum
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Enum, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class CategoriaCliente(str, enum.Enum):
    COMUM = "comum"
    PREMIUM = "premium"
    EMPRESARIAL = "empresarial"


class SituacaoCliente(str, enum.Enum):
    ATIVO = "ativo"
    BLOQUEADO = "bloqueado"


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(120), nullable=False)
    cpf = Column(String(14), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    categoria = Column(
        Enum(CategoriaCliente, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=CategoriaCliente.COMUM,
    )
    situacao = Column(
        Enum(SituacaoCliente, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=SituacaoCliente.ATIVO,
    )
    data_criacao = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    contas = relationship("Conta", back_populates="cliente", cascade="all, delete-orphan")
