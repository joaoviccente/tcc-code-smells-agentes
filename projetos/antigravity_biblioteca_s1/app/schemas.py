from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models import (
    CategoriaUsuario,
    SituacaoUsuario,
    EstadoExemplar,
    EstadoEmprestimo,
    EstadoReserva,
    EstadoMulta,
)

# ----------------- USUARIO -----------------

class UsuarioBase(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    matricula: str = Field(..., min_length=1, max_length=50)
    categoria: CategoriaUsuario

class UsuarioCreate(UsuarioBase):
    pass

class UsuarioUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    matricula: Optional[str] = Field(None, min_length=1, max_length=50)
    categoria: Optional[CategoriaUsuario] = None
    situacao: Optional[SituacaoUsuario] = None
    data_fim_suspensao: Optional[datetime] = None

class UsuarioResponse(BaseModel):
    id: int
    nome: str
    email: str
    matricula: str
    categoria: CategoriaUsuario
    situacao: SituacaoUsuario
    data_fim_suspensao: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ----------------- LIVRO -----------------

class LivroBase(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=255)
    autor: str = Field(..., min_length=1, max_length=255)
    isbn: str = Field(..., min_length=1, max_length=50)
    ano: int = Field(..., ge=0, le=2200)
    area_conhecimento: str = Field(..., min_length=1, max_length=100)

class LivroCreate(LivroBase):
    pass

class LivroUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=1, max_length=255)
    autor: Optional[str] = Field(None, min_length=1, max_length=255)
    isbn: Optional[str] = Field(None, min_length=1, max_length=50)
    ano: Optional[int] = Field(None, ge=0, le=2200)
    area_conhecimento: Optional[str] = Field(None, min_length=1, max_length=100)

class LivroResponse(LivroBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# ----------------- EXEMPLAR -----------------

class ExemplarBase(BaseModel):
    livro_id: int
    codigo_tombo: str = Field(..., min_length=1, max_length=50)
    estado: Optional[EstadoExemplar] = EstadoExemplar.disponivel

class ExemplarCreate(ExemplarBase):
    pass

class ExemplarUpdate(BaseModel):
    codigo_tombo: Optional[str] = Field(None, min_length=1, max_length=50)
    estado: Optional[EstadoExemplar] = None

class ExemplarResponse(BaseModel):
    id: int
    livro_id: int
    codigo_tombo: str
    estado: EstadoExemplar

    model_config = ConfigDict(from_attributes=True)


# ----------------- EMPRESTIMO -----------------

class EmprestimoCreate(BaseModel):
    usuario_id: int
    exemplar_id: int
    data_retirada: Optional[datetime] = None

class EmprestimoDevolver(BaseModel):
    data_devolucao: Optional[datetime] = None

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


# ----------------- RESERVA -----------------

class ReservaCreate(BaseModel):
    usuario_id: int
    livro_id: int

class ReservaResponse(BaseModel):
    id: int
    livro_id: int
    usuario_id: int
    exemplar_id: Optional[int] = None
    data: datetime
    posicao_fila: Optional[int] = None
    estado: EstadoReserva
    data_limite_retirada: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ----------------- MULTA -----------------

class MultaResponse(BaseModel):
    id: int
    emprestimo_id: int
    valor: Decimal
    estado: EstadoMulta
    data_geracao: datetime
    data_pagamento: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ----------------- RELATORIOS -----------------

class LivroMaisEmprestadoItem(BaseModel):
    livro_id: int
    titulo: str
    autor: str
    isbn: str
    area_conhecimento: str
    total_emprestimos: int

class UsuarioMaisAtrasosItem(BaseModel):
    usuario_id: int
    nome: str
    matricula: str
    categoria: CategoriaUsuario
    total_atrasos: int

class TaxaOcupacaoItem(BaseModel):
    area_conhecimento: str
    total_exemplares: int
    exemplares_emprestados: int
    taxa_ocupacao: float
