from pydantic import BaseModel, ConfigDict
from app.models.enums import CategoriaUsuario


class LivroMaisEmprestado(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    livro_id: int
    titulo: str
    autor: str
    isbn: str
    total_emprestimos: int


class UsuarioMaisAtrasos(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    usuario_id: int
    nome: str
    matricula: str
    categoria: CategoriaUsuario
    total_atrasos: int


class TaxaOcupacaoArea(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    area_conhecimento: str
    total_exemplares: int
    exemplares_emprestados: int
    taxa_ocupacao_percentual: float
