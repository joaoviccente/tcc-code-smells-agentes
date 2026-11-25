from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.relatorio import (
    LivroMaisEmprestadoResponse,
    UsuarioMaisAtrasosResponse,
    TaxaOcupacaoAcervoResponse,
)
from app.services import relatorio_service

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])


@router.get("/livros-mais-emprestados", response_model=List[LivroMaisEmprestadoResponse])
def relatorio_livros_mais_emprestados(
    data_inicio: Optional[datetime] = Query(None, description="Data de início do período (ISO format)"),
    data_fim: Optional[datetime] = Query(None, description="Data de fim do período (ISO format)"),
    limite: int = Query(10, ge=1, le=100, description="Quantidade máxima de livros a retornar"),
    db: Session = Depends(get_db)
):
    """
    Relatório de livros mais emprestados em um período especificado.
    """
    return relatorio_service.get_livros_mais_emprestados(
        db, data_inicio=data_inicio, data_fim=data_fim, limite=limite
    )


@router.get("/usuarios-mais-atrasos", response_model=List[UsuarioMaisAtrasosResponse])
def relatorio_usuarios_com_mais_atrasos(
    limite: int = Query(10, ge=1, le=100, description="Quantidade máxima de usuários a retornar"),
    db: Session = Depends(get_db)
):
    """
    Relatório de usuários com mais ocorrências de atraso e total de dias em atraso.
    """
    return relatorio_service.get_usuarios_mais_atrasos(db, limite=limite)


@router.get("/taxa-ocupacao-acervo", response_model=List[TaxaOcupacaoAcervoResponse])
def relatorio_taxa_ocupacao_acervo(db: Session = Depends(get_db)):
    """
    Relatório da taxa de ocupação do acervo (% de exemplares emprestados) agrupada por área de conhecimento.
    """
    return relatorio_service.get_taxa_ocupacao_acervo(db)
