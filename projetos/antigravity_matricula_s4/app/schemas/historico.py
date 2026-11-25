from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.config import SituacaoHistorico


class HistoricoCreate(BaseModel):
    aluno_id: int = Field(..., description="ID do aluno")
    disciplina_id: int = Field(..., description="ID da disciplina")
    semestre: str = Field(..., min_length=4, max_length=20, description="Semestre letivo (ex: '2025.2')")
    nota: Optional[float] = Field(None, ge=0.0, le=10.0, description="Nota final (0.0 a 10.0)")
    situacao: SituacaoHistorico = Field(..., description="aprovado, reprovado, reprovado_por_falta, trancado")


class HistoricoResponse(BaseModel):
    id: int
    aluno_id: int
    disciplina_id: int
    disciplina_codigo: Optional[str] = None
    disciplina_nome: Optional[str] = None
    semestre: str
    nota: Optional[float] = None
    situacao: SituacaoHistorico

    model_config = ConfigDict(from_attributes=True)
