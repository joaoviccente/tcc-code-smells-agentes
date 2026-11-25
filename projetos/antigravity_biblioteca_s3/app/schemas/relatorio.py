from decimal import Decimal
from pydantic import BaseModel, ConfigDict
from app.models.enums import CategoriaUsuario


class LivroMaisEmprestadoResponse(BaseModel):
    livro_id: int
    titulo: str
    autor: str
    isbn: str
    total_emprestimos: int

    model_config = ConfigDict(from_attributes=True)


class UsuarioMaisAtrasosResponse(BaseModel):
    usuario_id: int
    nome: str
    matricula: str
    categoria: CategoriaUsuario
    total_atrasos: int
    total_dias_atraso: int

    model_config = ConfigDict(from_attributes=True)


class TaxaOcupacaoAcervoResponse(BaseModel):
    area: str
    total_exemplares: int
    exemplares_emprestados: int
    exemplares_disponiveis: int
    taxa_ocupacao_percentual: float

    model_config = ConfigDict(from_attributes=True)
