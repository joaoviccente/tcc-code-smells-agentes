from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.relatorio import (
    LivroMaisEmprestado,
    TaxaOcupacaoArea,
    UsuarioMaisAtrasos,
)
from app.services import relatorio_service

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])


@router.get("/livros-mais-emprestados", response_model=List[LivroMaisEmprestado])
def relatorio_livros_mais_emprestados(
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
    limite: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return relatorio_service.relatorio_livros_mais_emprestados(
        db, data_inicio=data_inicio, data_fim=data_fim, limite=limite
    )


@router.get("/usuarios-mais-atrasos", response_model=List[UsuarioMaisAtrasos])
def relatorio_usuarios_mais_atrasos(
    limite: int = Query(10, ge=1, le=100),
    data_referencia: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    return relatorio_service.relatorio_usuarios_mais_atrasos(
        db, limite=limite, data_referencia=data_referencia
    )


@router.get("/taxa-ocupacao", response_model=List[TaxaOcupacaoArea])
def relatorio_taxa_ocupacao(db: Session = Depends(get_db)):
    return relatorio_service.relatorio_taxa_ocupacao_por_area(db)
