from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from app.models.enums import SituacaoHistorico
from app.schemas.disciplina import DisciplinaSimple

class HistoricoBase(BaseModel):
    aluno_id: int = Field(..., description="ID do aluno")
    disciplina_id: int = Field(..., description="ID da disciplina")
    semestre: str = Field(..., min_length=4, max_length=20, description="Semestre letivo (ex: 2025.2)")
    nota: Optional[float] = Field(None, ge=0.0, le=10.0, description="Nota final (0.0 a 10.0)")
    situacao: SituacaoHistorico = Field(..., description="Situação final: aprovado, reprovado, reprovado_por_falta, trancado")

class HistoricoCreate(HistoricoBase):
    pass

class HistoricoResponse(HistoricoBase):
    id: int
    disciplina: Optional[DisciplinaSimple] = None

    model_config = ConfigDict(from_attributes=True)
