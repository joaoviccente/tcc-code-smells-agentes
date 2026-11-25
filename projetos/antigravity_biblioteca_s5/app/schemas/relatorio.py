from pydantic import BaseModel, Field


class LivroMaisEmprestadoResponse(BaseModel):
    livro_id: int
    titulo: str
    autor: str
    area_conhecimento: str
    total_emprestimos: int


class UsuarioMaisAtrasosResponse(BaseModel):
    usuario_id: int
    nome: str
    matricula: str
    categoria: str
    total_atrasos: int


class TaxaOcupacaoAreaResponse(BaseModel):
    area_conhecimento: str
    total_exemplares: int
    exemplares_emprestados: int
    taxa_ocupacao_percentual: float = Field(..., description="Percentual de ocupação (0 a 100%)")
