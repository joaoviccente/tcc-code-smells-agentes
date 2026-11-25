from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoReserva
from app.utils import get_utcnow


class Reserva(Base):
    __tablename__ = "reservas"

    id = Column(Integer, primary_key=True, index=True)
    livro_id = Column(Integer, ForeignKey("livros.id", ondelete="CASCADE"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    exemplar_id = Column(Integer, ForeignKey("exemplares.id", ondelete="SET NULL"), nullable=True)
    data = Column(DateTime, nullable=False, default=get_utcnow)
    posicao_fila = Column(Integer, nullable=True)
    estado = Column(SQLEnum(EstadoReserva), nullable=False, default=EstadoReserva.AGUARDANDO)
    data_limite_retirada = Column(DateTime, nullable=True)

    livro = relationship("Livro", back_populates="reservas")
    usuario = relationship("Usuario", back_populates="reservas")
    exemplar = relationship("Exemplar", back_populates="reservas")
