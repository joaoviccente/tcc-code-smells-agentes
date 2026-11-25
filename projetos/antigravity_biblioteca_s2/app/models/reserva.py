from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoReserva


class Reserva(Base):
    __tablename__ = "reservas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    livro_id = Column(Integer, ForeignKey("livros.id", ondelete="CASCADE"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    data = Column(DateTime(timezone=True), nullable=False)
    posicao_fila = Column(Integer, default=1, nullable=False)
    estado = Column(Enum(EstadoReserva), default=EstadoReserva.AGUARDANDO, nullable=False)
    data_disponibilizacao = Column(DateTime(timezone=True), nullable=True)
    data_limite_retirada = Column(DateTime(timezone=True), nullable=True)

    livro = relationship("Livro", back_populates="reservas")
    usuario = relationship("Usuario", back_populates="reservas")
