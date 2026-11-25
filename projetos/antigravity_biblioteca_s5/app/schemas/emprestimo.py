from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.config import EstadoEmprestimo


class EmprestimoCreate(BaseModel):
    usuario_id: int = Field(..., gt=0, examples=[1])
    exemplar_id: int = Field(..., gt=0, examples=[1])
    data_retirada: datetime | None = Field(
        default=None,
        description="Data de retirada opcional (padrão é agora)",
    )


class EmprestimoDevolucao(BaseModel):
    data_devolucao: datetime | None = Field(
        default=None,
        description="Data de devolução opcional (padrão é agora)",
    )


class EmprestimoResponse(BaseModel):
    id: int
    exemplar_id: int
    usuario_id: int
    data_retirada: datetime
    data_prevista: datetime
    data_devolucao: datetime | None
    estado: EstadoEmprestimo
    numero_renovacoes: int

    model_config = ConfigDict(from_attributes=True)
