from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoEmprestimo
from app.utils import get_utcnow


class Emprestimo(Base):
    __tablename__ = "emprestimos"

    id = Column(Integer, primary_key=True, index=True)
    exemplar_id = Column(Integer, ForeignKey("exemplares.id", ondelete="CASCADE"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    data_retirada = Column(DateTime, nullable=False, default=get_utcnow)
    data_prevista = Column(DateTime, nullable=False)
    data_devolucao = Column(DateTime, nullable=True)
    estado = Column(SQLEnum(EstadoEmprestimo), nullable=False, default=EstadoEmprestimo.ATIVO)
    numero_renovacoes = Column(Integer, nullable=False, default=0)

    exemplar = relationship("Exemplar", back_populates="emprestimos")
    usuario = relationship("Usuario", back_populates="emprestimos")
    multa = relationship("Multa", back_populates="emprestimo", uselist=False, cascade="all, delete-orphan")
