from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..erros import ErroNegocio
from ..models import Emprestimo, Exemplar, Livro, Usuario
from ..schemas import LivroMaisEmprestado, OcupacaoArea, UsuarioAtrasos

router = APIRouter(prefix="/relatorios", tags=["Relatorios"])


@router.get("/livros-mais-emprestados", response_model=list[LivroMaisEmprestado])
def livros_mais_emprestados(
    inicio: date = Query(..., description="Data inicial (inclusive), AAAA-MM-DD"),
    fim: date = Query(..., description="Data final (inclusive), AAAA-MM-DD"),
    limite: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    if inicio > fim:
        raise ErroNegocio("'inicio' deve ser anterior ou igual a 'fim'", 422, "periodo_invalido")
    de, ate = datetime.combine(inicio, time.min), datetime.combine(fim + timedelta(days=1), time.min)
    total = func.count(Emprestimo.id).label("total")
    q = (
        select(Livro.id, Livro.titulo, Livro.autor, total)
        .join(Exemplar, Exemplar.livro_id == Livro.id)
        .join(Emprestimo, Emprestimo.exemplar_id == Exemplar.id)
        .where(Emprestimo.data_retirada >= de, Emprestimo.data_retirada < ate)
        .group_by(Livro.id, Livro.titulo, Livro.autor)
        .order_by(total.desc(), Livro.titulo)
        .limit(limite)
    )
    return [LivroMaisEmprestado(livro_id=i, titulo=t, autor=a, total_emprestimos=n)
            for i, t, a, n in db.execute(q)]


@router.get("/usuarios-mais-atrasos", response_model=list[UsuarioAtrasos])
def usuarios_mais_atrasos(
    limite: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Ranking por quantidade de emprestimos em atraso (devolvidos com atraso ou ainda atrasados)."""
    qtd = func.count(Emprestimo.id).label("qtd")
    dias = func.sum(Emprestimo.dias_atraso).label("dias")
    q = (
        select(Usuario.id, Usuario.nome, Usuario.matricula, Usuario.categoria, qtd, dias)
        .join(Emprestimo, Emprestimo.usuario_id == Usuario.id)
        .where(Emprestimo.dias_atraso > 0)
        .group_by(Usuario.id, Usuario.nome, Usuario.matricula, Usuario.categoria)
        .order_by(qtd.desc(), dias.desc(), Usuario.nome)
        .limit(limite)
    )
    return [UsuarioAtrasos(usuario_id=i, nome=n, matricula=m, categoria=c,
                           quantidade_atrasos=q_, total_dias_atraso=d or 0)
            for i, n, m, c, q_, d in db.execute(q)]


@router.get("/ocupacao-acervo", response_model=list[OcupacaoArea])
def ocupacao_acervo(db: Session = Depends(get_db)):
    """Taxa de ocupacao por area = emprestados / exemplares ativos (baixados excluidos)."""
    def conta(estado):
        return func.sum(case((Exemplar.estado == estado, 1), else_=0))

    q = (
        select(
            Livro.area_conhecimento,
            func.count(Exemplar.id),
            conta("emprestado"), conta("reservado"), conta("disponivel"), conta("em_reparo"),
        )
        .join(Exemplar, Exemplar.livro_id == Livro.id)
        .where(Exemplar.estado != "baixado")
        .group_by(Livro.area_conhecimento)
        .order_by(Livro.area_conhecimento)
    )
    resultado = []
    for area, total, emp, res, disp, rep in db.execute(q):
        resultado.append(OcupacaoArea(
            area_conhecimento=area, total_exemplares=total, emprestados=emp or 0,
            reservados=res or 0, disponiveis=disp or 0, em_reparo=rep or 0,
            taxa_ocupacao=round(100 * (emp or 0) / total, 2) if total else 0.0,
        ))
    return resultado
