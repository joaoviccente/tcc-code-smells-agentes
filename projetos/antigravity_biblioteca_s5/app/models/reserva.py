from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.config import EstadoReserva
from app.database import Base


class Reserva(Base):
    __tablename__ = "reservas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    livro_id = Column(Integer, ForeignKey("livros.id", ondelete="CASCADE"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    data_reserva = Column(DateTime, nullable=False)
    posicao_fila = Column(Integer, nullable=False, default=1)
    estado = Column(Enum(EstadoReserva), default=EstadoReserva.AGUARDANDO, nullable=False)
    data_disponibilizacao = Column(DateTime, nullable=True)
    exemplar_id = Column(Integer, ForeignKey("exemplares.id", ondelete="SET NULL"), nullable=True)

    livro = relationship("Livro", back_populates="reservas")
    usuario = relationship("Usuario", back_populates="reservas")
    exemplar = relationship("Exemplar")
