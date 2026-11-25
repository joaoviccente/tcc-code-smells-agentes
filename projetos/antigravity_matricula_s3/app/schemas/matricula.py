from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.enums import EstadoMatricula, CategoriaAluno
from app.schemas.aluno import AlunoResponse
from app.schemas.turma import TurmaResponse

class MatriculaCreate(BaseModel):
    aluno_id: int
    turma_id: int

class MatriculaAction(BaseModel):
    data_referencia: Optional[datetime] = None  # Permite simular operações em datas futuras para testes

class MatriculaResponse(BaseModel):
    id: int
    aluno_id: int
    turma_id: int
    data: datetime
    estado: EstadoMatricula
    data_limite_confirmacao: Optional[datetime] = None
    aluno: Optional[AlunoResponse] = None
    turma: Optional[TurmaResponse] = None

    model_config = ConfigDict(from_attributes=True)

class FilaEsperaItem(BaseModel):
    posicao: int
    matricula_id: int
    aluno_id: int
    aluno_nome: str
    aluno_matricula: str
    categoria: CategoriaAluno
    prioridade_categoria: int
    data_solicitacao: datetime
    data_limite_confirmacao: Optional[datetime] = None

class FilaEsperaResponse(BaseModel):
    turma_id: int
    total_na_fila: int
    fila: List[FilaEsperaItem]
