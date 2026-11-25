from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.prerequisito import PreRequisito

class Disciplina(Base):
    __tablename__ = "disciplinas"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(20), unique=True, index=True, nullable=False)
    nome = Column(String(150), nullable=False)
    numero_creditos = Column(Integer, nullable=False)
    carga_horaria = Column(Integer, nullable=False)
    departamento = Column(String(100), nullable=False)

    turmas = relationship("Turma", back_populates="disciplina", cascade="all, delete-orphan")
    historicos = relationship("Historico", back_populates="disciplina", cascade="all, delete-orphan")

    # Disciplinas que esta disciplina exige como pré-requisito
    prerequisitos = relationship(
        "Disciplina",
        secondary="prerequisitos",
        primaryjoin="Disciplina.id==PreRequisito.disciplina_id",
        secondaryjoin="Disciplina.id==PreRequisito.prerequisito_id",
        backref="exigida_como_prerequisito_por"
    )

    def __repr__(self):
        return f"<Disciplina(id={self.id}, codigo='{self.codigo}', nome='{self.nome}', creditos={self.numero_creditos})>"
