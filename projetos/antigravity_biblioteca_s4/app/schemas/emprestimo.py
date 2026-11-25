from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from app.models.enums import EstadoEmprestimo


class EmprestimoCreate(BaseModel):
    exemplar_id: int = Field(..., description="ID do exemplar a ser emprestado")
    usuario_id: int = Field(..., description="ID do usuário que realiza o empréstimo")
    data_retirada: Optional[datetime] = Field(default=None, description="Data de retirada (opcional, padrão: data/hora atual)")


class EmprestimoRenovar(BaseModel):
    data_renovacao: Optional[datetime] = Field(default=None, description="Data da tentativa de renovação (opcional, padrão: data/hora atual)")


class EmprestimoDevolver(BaseModel):
    data_devolucao: Optional[datetime] = Field(default=None, description="Data de devolução (opcional, padrão: data/hora atual)")


class EmprestimoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exemplar_id: int
    usuario_id: int
    data_retirada: datetime
    data_prevista: datetime
    data_devolucao: Optional[datetime] = None
    estado: EstadoEmprestimo
    numero_de_renovacoes: int
