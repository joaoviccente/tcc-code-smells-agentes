from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoEmprestimo


class Emprestimo(Base):
    __tablename__ = "emprestimos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    exemplar_id = Column(Integer, ForeignKey("exemplares.id", ondelete="RESTRICT"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    data_retirada = Column(DateTime(timezone=True), nullable=False)
    data_prevista = Column(DateTime(timezone=True), nullable=False)
    data_devolucao = Column(DateTime(timezone=True), nullable=True)
    estado = Column(Enum(EstadoEmprestimo), default=EstadoEmprestimo.ATIVO, nullable=False)
    numero_renovacoes = Column(Integer, default=0, nullable=False)

    exemplar = relationship("Exemplar", back_populates="emprestimos")
    usuario = relationship("Usuario", back_populates="emprestimos")
    multa = relationship("Multa", back_populates="emprestimo", uselist=False, cascade="all, delete-orphan")
