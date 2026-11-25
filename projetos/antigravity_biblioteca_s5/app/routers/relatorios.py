from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.relatorio import (
    LivroMaisEmprestadoResponse,
    TaxaOcupacaoAreaResponse,
    UsuarioMaisAtrasosResponse,
)
from app.services import relatorio_service

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])


@router.get("/livros-mais-emprestados", response_model=list[LivroMaisEmprestadoResponse])
def relatorio_livros_mais_emprestados(
    data_inicio: datetime = Query(..., description="Data de início do período (ISO-8601)"),
    data_fim: datetime = Query(..., description="Data de fim do período (ISO-8601)"),
    limite: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return relatorio_service.relatorio_livros_mais_emprestados(
        db,
        data_inicio=data_inicio,
        data_fim=data_fim,
        limite=limite,
    )


@router.get("/usuarios-mais-atrasos", response_model=list[UsuarioMaisAtrasosResponse])
def relatorio_usuarios_mais_atrasos(
    limite: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return relatorio_service.relatorio_usuarios_com_mais_atrasos(db, limite=limite)


@router.get("/taxa-ocupacao", response_model=list[TaxaOcupacaoAreaResponse])
def relatorio_taxa_ocupacao(db: Session = Depends(get_db)):
    return relatorio_service.relatorio_taxa_ocupacao_por_area(db)
