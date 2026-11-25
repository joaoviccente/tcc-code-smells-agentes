from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.config import EstadoEmprestimo
from app.database import Base


class Emprestimo(Base):
    __tablename__ = "emprestimos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    exemplar_id = Column(Integer, ForeignKey("exemplares.id"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    data_retirada = Column(DateTime, nullable=False)
    data_prevista = Column(DateTime, nullable=False)
    data_devolucao = Column(DateTime, nullable=True)
    estado = Column(Enum(EstadoEmprestimo), default=EstadoEmprestimo.ATIVO, nullable=False)
    numero_renovacoes = Column(Integer, default=0, nullable=False)

    exemplar = relationship("Exemplar", back_populates="emprestimos")
    usuario = relationship("Usuario", back_populates="emprestimos")
    multas = relationship("Multa", back_populates="emprestimo", cascade="all, delete-orphan")
