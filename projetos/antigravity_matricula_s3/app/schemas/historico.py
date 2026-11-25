from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import SituacaoHistorico

class HistoricoBase(BaseModel):
    aluno_id: int
    disciplina_id: int
    semestre: str
    nota: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    situacao: SituacaoHistorico
    observacao: Optional[str] = None

class HistoricoCreate(HistoricoBase):
    pass

class HistoricoResponse(HistoricoBase):
    id: int
    disciplina_codigo: Optional[str] = None
    disciplina_nome: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
