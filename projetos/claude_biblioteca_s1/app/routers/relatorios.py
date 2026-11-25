from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import servicos
from app.deps import get_db
from app.schemas import LivroMaisEmprestado, OcupacaoArea, UsuarioAtrasos

router = APIRouter(prefix="/relatorios", tags=["Relatorios"])


@router.get("/livros-mais-emprestados", response_model=list[LivroMaisEmprestado])
def livros_mais_emprestados(inicio: date, fim: date, limite: int = Query(10, ge=1, le=100),
                            db: Session = Depends(get_db)):
    if inicio > fim:
        raise HTTPException(422, "'inicio' deve ser anterior ou igual a 'fim'")
    return servicos.relatorio_mais_emprestados(db, inicio, fim, limite)


@router.get("/usuarios-com-mais-atrasos", response_model=list[UsuarioAtrasos])
def usuarios_com_mais_atrasos(limite: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    return servicos.relatorio_usuarios_atrasos(db, limite)


@router.get("/ocupacao-por-area", response_model=list[OcupacaoArea])
def ocupacao_por_area(db: Session = Depends(get_db)):
    return servicos.relatorio_ocupacao(db)
