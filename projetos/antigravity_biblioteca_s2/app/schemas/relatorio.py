from pydantic import BaseModel, ConfigDict
from app.models.enums import CategoriaUsuario


class LivroMaisEmprestado(BaseModel):
    livro_id: int
    titulo: str
    autor: str
    isbn: str
    total_emprestimos: int

    model_config = ConfigDict(from_attributes=True)


class UsuarioMaisAtrasos(BaseModel):
    usuario_id: int
    nome: str
    matricula: str
    categoria: CategoriaUsuario
    total_atrasos: int
    total_dias_atraso: int

    model_config = ConfigDict(from_attributes=True)


class TaxaOcupacaoArea(BaseModel):
    area_conhecimento: str
    total_exemplares: int
    exemplares_emprestados: int
    taxa_ocupacao_percentual: float

    model_config = ConfigDict(from_attributes=True)
