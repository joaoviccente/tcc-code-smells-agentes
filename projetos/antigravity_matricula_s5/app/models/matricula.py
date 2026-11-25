from sqlalchemy import Column, Integer, DateTime, Enum as SQLEnum, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.enums import EstadoMatricula

class Matricula(Base):
    __tablename__ = "matriculas"

    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id", ondelete="CASCADE"), nullable=False, index=True)
    turma_id = Column(Integer, ForeignKey("turmas.id", ondelete="CASCADE"), nullable=False, index=True)
    data = Column(DateTime(timezone=True), nullable=False, default=func.now(), server_default=func.now())
    estado = Column(SQLEnum(EstadoMatricula), nullable=False, default=EstadoMatricula.SOLICITADA, index=True)

    # Controle de liberação de vaga para lista de espera (48h para confirmar)
    vaga_liberada_em = Column(DateTime(timezone=True), nullable=True)
    limite_confirmacao_em = Column(DateTime(timezone=True), nullable=True)

    aluno = relationship("Aluno", back_populates="matriculas")
    turma = relationship("Turma", back_populates="matriculas")

    def __repr__(self):
        return f"<Matricula(id={self.id}, aluno_id={self.aluno_id}, turma_id={self.turma_id}, estado='{self.estado}')>"
