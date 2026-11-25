from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from app.models.enums import EstadoMatricula, CategoriaAluno
from app.schemas.aluno import AlunoResponse
from app.schemas.turma import TurmaResponse

class MatriculaSolicitacao(BaseModel):
    aluno_id: int = Field(..., description="ID do aluno solicitante")
    turma_id: int = Field(..., description="ID da turma desejada")
    auto_confirm: bool = Field(default=True, description="Se houver vaga imediata, confirma automaticamente")

class MatriculaActionRequest(BaseModel):
    data_referencia: Optional[datetime] = Field(
        None,
        description="Data de referência para cálculo de prazos (se nulo, usa a data/hora atual)"
    )

class MatriculaResponse(BaseModel):
    id: int
    aluno_id: int
    turma_id: int
    data: datetime
    estado: EstadoMatricula
    vaga_liberada_em: Optional[datetime] = None
    limite_confirmacao_em: Optional[datetime] = None
    posicao_fila: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class MatriculaDetailResponse(MatriculaResponse):
    aluno: Optional[AlunoResponse] = None
    turma: Optional[TurmaResponse] = None

class WaitlistEntryResponse(BaseModel):
    posicao: int
    matricula_id: int
    aluno_id: int
    aluno_nome: str
    aluno_matricula: str
    categoria: CategoriaAluno
    prioridade_categoria: int
    data_solicitacao: datetime
    vaga_liberada_em: Optional[datetime] = None
    limite_confirmacao_em: Optional[datetime] = None
    aguardando_confirmacao: bool = False

    model_config = ConfigDict(from_attributes=True)

class FilaEsperaResponse(BaseModel):
    turma_id: int
    disciplina_nome: str
    semestre: str
    total_na_fila: int
    fila: list[WaitlistEntryResponse]
