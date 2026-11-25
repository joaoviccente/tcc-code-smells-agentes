from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import (
    LivroMaisEmprestadoItem,
    UsuarioMaisAtrasosItem,
    TaxaOcupacaoItem,
)
import app.services as services

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])

@router.get("/livros-mais-emprestados", response_model=List[LivroMaisEmprestadoItem], status_code=status.HTTP_200_OK)
def livros_mais_emprestados(
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    return services.relatorio_livros_mais_emprestados(
        db,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )

@router.get("/usuarios-mais-atrasos", response_model=List[UsuarioMaisAtrasosItem], status_code=status.HTTP_200_OK)
def usuarios_mais_atrasos(db: Session = Depends(get_db)):
    return services.relatorio_usuarios_mais_atrasos(db)

@router.get("/taxa-ocupacao-acervo", response_model=List[TaxaOcupacaoItem], status_code=status.HTTP_200_OK)
def taxa_ocupacao_acervo(db: Session = Depends(get_db)):
    return services.relatorio_taxa_ocupacao_acervo(db)
