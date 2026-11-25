from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.models.enums import SituacaoHistorico


class HistoricoBase(BaseModel):
    aluno_id: int = Field(..., description="ID do aluno")
    disciplina_id: int = Field(..., description="ID da disciplina")
    semestre: str = Field(..., min_length=1, max_length=20, description="Semestre letivo (ex: 2025.2)")
    nota: Optional[float] = Field(None, ge=0.0, le=10.0, description="Nota obtida (0.0 a 10.0)")
    situacao: SituacaoHistorico = Field(..., description="Situação: aprovado, reprovado, trancado, reprovado_por_falta")


class HistoricoCreate(HistoricoBase):
    pass


class HistoricoUpdate(BaseModel):
    semestre: Optional[str] = Field(None, min_length=1, max_length=20)
    nota: Optional[float] = Field(None, ge=0.0, le=10.0)
    situacao: Optional[SituacaoHistorico] = None


class HistoricoResponse(HistoricoBase):
    id: int
    disciplina_codigo: Optional[str] = None
    disciplina_nome: Optional[str] = None
    aluno_nome: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
