from sqlalchemy import Column, Integer, Float, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoMulta


class Multa(Base):
    __tablename__ = "multas"

    id = Column(Integer, primary_key=True, index=True)
    emprestimo_id = Column(Integer, ForeignKey("emprestimos.id", ondelete="CASCADE"), nullable=False)
    valor = Column(Float, nullable=False)
    estado = Column(SQLEnum(EstadoMulta), default=EstadoMulta.ABERTA, nullable=False)

    emprestimo = relationship("Emprestimo", back_populates="multas")
