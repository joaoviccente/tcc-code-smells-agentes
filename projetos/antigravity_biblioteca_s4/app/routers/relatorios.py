from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.relatorio import (
    LivroMaisEmprestado,
    UsuarioMaisAtrasos,
    TaxaOcupacaoArea,
)
from app.services import relatorio_service

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])


@router.get(
    "/livros-mais-emprestados",
    response_model=List[LivroMaisEmprestado],
    status_code=status.HTTP_200_OK,
)
def relatorio_livros_mais_emprestados(
    data_inicio: datetime = Query(..., description="Data de início do período (ISO format: YYYY-MM-DDTHH:MM:SS ou YYYY-MM-DD)"),
    data_fim: datetime = Query(..., description="Data de término do período (ISO format: YYYY-MM-DDTHH:MM:SS ou YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """Relatório de livros mais emprestados em um período."""
    return relatorio_service.relatorio_livros_mais_emprestados(db, data_inicio, data_fim)


@router.get(
    "/usuarios-mais-atrasos",
    response_model=List[UsuarioMaisAtrasos],
    status_code=status.HTTP_200_OK,
)
def relatorio_usuarios_mais_atrasos(db: Session = Depends(get_db)):
    """Relatório de usuários com maior número de empréstimos em atraso."""
    return relatorio_service.relatorio_usuarios_mais_atrasos(db)


@router.get(
    "/taxa-ocupacao",
    response_model=List[TaxaOcupacaoArea],
    status_code=status.HTTP_200_OK,
)
def relatorio_taxa_ocupacao(db: Session = Depends(get_db)):
    """Relatório da taxa de ocupação do acervo por área de conhecimento."""
    return relatorio_service.relatorio_taxa_ocupacao_acervo(db)


@router.get(
    "/taxa-ocupacao-acervo",
    response_model=List[TaxaOcupacaoArea],
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def relatorio_taxa_ocupacao_alias(db: Session = Depends(get_db)):
    """Alias para taxa de ocupação do acervo por área de conhecimento."""
    return relatorio_service.relatorio_taxa_ocupacao_acervo(db)
