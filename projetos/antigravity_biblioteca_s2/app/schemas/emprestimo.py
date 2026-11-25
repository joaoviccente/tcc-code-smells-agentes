from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import EstadoEmprestimo


class EmprestimoCreate(BaseModel):
    exemplar_id: int = Field(..., gt=0, description="ID do exemplar a ser emprestado")
    usuario_id: int = Field(..., gt=0, description="ID do usuário que realiza o empréstimo")
    data_retirada: Optional[datetime] = Field(None, description="Data/hora de retirada (padrão: agora)")


class EmprestimoRenovar(BaseModel):
    data_renovacao: Optional[datetime] = Field(None, description="Data/hora da renovação (padrão: agora)")


class EmprestimoDevolver(BaseModel):
    data_devolucao: Optional[datetime] = Field(None, description="Data/hora da devolução (padrão: agora)")


class EmprestimoResponse(BaseModel):
    id: int
    exemplar_id: int
    usuario_id: int
    data_retirada: datetime
    data_prevista: datetime
    data_devolucao: Optional[datetime] = None
    estado: EstadoEmprestimo
    numero_renovacoes: int

    model_config = ConfigDict(from_attributes=True)
