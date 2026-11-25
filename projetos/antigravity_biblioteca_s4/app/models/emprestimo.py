from sqlalchemy import Column, Integer, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoEmprestimo


class Emprestimo(Base):
    __tablename__ = "emprestimos"

    id = Column(Integer, primary_key=True, index=True)
    exemplar_id = Column(Integer, ForeignKey("exemplares.id", ondelete="CASCADE"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    data_retirada = Column(DateTime, nullable=False)
    data_prevista = Column(DateTime, nullable=False)
    data_devolucao = Column(DateTime, nullable=True)
    estado = Column(SQLEnum(EstadoEmprestimo), default=EstadoEmprestimo.ATIVO, nullable=False)
    numero_de_renovacoes = Column(Integer, default=0, nullable=False)

    exemplar = relationship("Exemplar", back_populates="emprestimos")
    usuario = relationship("Usuario", back_populates="emprestimos")
    multas = relationship("Multa", back_populates="emprestimo", cascade="all, delete-orphan")
