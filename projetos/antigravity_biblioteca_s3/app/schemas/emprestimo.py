from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import EstadoEmprestimo
from app.schemas.multa import MultaResponse


class EmprestimoCreate(BaseModel):
    usuario_id: int = Field(..., gt=0, description="ID do usuário solicitante")
    exemplar_id: int = Field(..., gt=0, description="ID do exemplar a ser emprestado")
    data_retirada: Optional[datetime] = Field(default=None, description="Data/hora da retirada (opcional, padrão atual)")


class EmprestimoDevolucao(BaseModel):
    data_devolucao: Optional[datetime] = Field(default=None, description="Data/hora da devolução (opcional, padrão atual)")


class EmprestimoResponse(BaseModel):
    id: int
    exemplar_id: int
    usuario_id: int
    data_retirada: datetime
    data_prevista: datetime
    data_devolucao: Optional[datetime] = None
    estado: EstadoEmprestimo
    numero_renovacoes: int
    multa: Optional[MultaResponse] = None

    model_config = ConfigDict(from_attributes=True)
