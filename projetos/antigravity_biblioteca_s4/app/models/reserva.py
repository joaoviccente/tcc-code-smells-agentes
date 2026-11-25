from sqlalchemy import Column, Integer, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoReserva


class Reserva(Base):
    __tablename__ = "reservas"

    id = Column(Integer, primary_key=True, index=True)
    livro_id = Column(Integer, ForeignKey("livros.id", ondelete="CASCADE"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    data = Column(DateTime, nullable=False)
    posicao_na_fila = Column(Integer, nullable=True)
    estado = Column(SQLEnum(EstadoReserva), default=EstadoReserva.AGUARDANDO, nullable=False)
    data_limite_retirada = Column(DateTime, nullable=True)
    exemplar_id = Column(Integer, ForeignKey("exemplares.id", ondelete="SET NULL"), nullable=True)

    livro = relationship("Livro", back_populates="reservas")
    usuario = relationship("Usuario", back_populates="reservas")
    exemplar = relationship("Exemplar", back_populates="reservas_atribuidas")
