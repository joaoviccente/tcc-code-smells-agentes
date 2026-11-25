from collections import defaultdict
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import Emprestimo, Exemplar, Livro, Usuario
from ..schemas import LivroMaisEmprestado, OcupacaoArea, UsuarioAtrasos
from ..servicos import dias_atraso

router = APIRouter(prefix="/relatorios", tags=["Relatorios"])


def _validar_periodo(inicio: date | None, fim: date | None) -> None:
    if inicio and fim and inicio > fim:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="'inicio' deve ser anterior ou igual a 'fim'")


@router.get("/livros-mais-emprestados", response_model=list[LivroMaisEmprestado])
def livros_mais_emprestados(
    inicio: date = Query(..., description="Data inicial (inclusiva) da retirada, AAAA-MM-DD"),
    fim: date = Query(..., description="Data final (inclusiva) da retirada, AAAA-MM-DD"),
    limite: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _validar_periodo(inicio, fim)
    total = func.count(Emprestimo.id).label("total")
    linhas = db.execute(
        select(Livro.id, Livro.titulo, Livro.autor, total)
        .join(Exemplar, Exemplar.livro_id == Livro.id)
        .join(Emprestimo, Emprestimo.exemplar_id == Exemplar.id)
        .where(
            Emprestimo.data_retirada >= datetime.combine(inicio, time.min),
            Emprestimo.data_retirada < datetime.combine(fim + timedelta(days=1), time.min),
        )
        .group_by(Livro.id, Livro.titulo, Livro.autor)
        .order_by(total.desc(), Livro.titulo, Livro.id)
        .limit(limite)
    ).all()
    return [
        LivroMaisEmprestado(livro_id=i, titulo=t, autor=a, total_emprestimos=n) for i, t, a, n in linhas
    ]


@router.get("/usuarios-mais-atrasos", response_model=list[UsuarioAtrasos])
def usuarios_com_mais_atrasos(
    inicio: date | None = Query(None, description="Considera emprestimos retirados a partir desta data"),
    fim: date | None = Query(None, description="Considera emprestimos retirados ate esta data"),
    limite: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Conta emprestimos devolvidos com atraso e emprestimos atualmente atrasados."""
    _validar_periodo(inicio, fim)
    q = select(Emprestimo).join(Usuario)
    if inicio:
        q = q.where(Emprestimo.data_retirada >= datetime.combine(inicio, time.min))
    if fim:
        q = q.where(Emprestimo.data_retirada < datetime.combine(fim + timedelta(days=1), time.min))

    acumulado: dict[int, list] = defaultdict(lambda: [None, 0, 0])
    for emp in db.scalars(q):
        dias = dias_atraso(emp)
        if dias <= 0:
            continue
        item = acumulado[emp.usuario_id]
        item[0] = emp.usuario
        item[1] += 1
        item[2] += dias

    ranking = sorted(acumulado.values(), key=lambda x: (-x[1], -x[2], x[0].nome))[:limite]
    return [
        UsuarioAtrasos(
            usuario_id=u.id, nome=u.nome, matricula=u.matricula, categoria=u.categoria,
            total_atrasos=n, total_dias_atraso=d,
        )
        for u, n, d in ranking
    ]


@router.get("/ocupacao-acervo", response_model=list[OcupacaoArea])
def ocupacao_por_area(db: Session = Depends(get_db)):
    """Taxa de ocupacao = exemplares emprestados / exemplares do acervo ativo (exclui baixados)."""
    def contar(estado: str):
        return func.sum(case((Exemplar.estado == estado, 1), else_=0))

    linhas = db.execute(
        select(
            Livro.area_conhecimento,
            func.count(Exemplar.id),
            contar("emprestado"),
            contar("reservado"),
            contar("disponivel"),
            contar("em_reparo"),
            contar("baixado"),
        )
        .join(Exemplar, Exemplar.livro_id == Livro.id)
        .group_by(Livro.area_conhecimento)
        .order_by(Livro.area_conhecimento)
    ).all()

    resultado = []
    for area, total, emp, res, disp, rep, baix in linhas:
        acervo_ativo = total - baix
        taxa = round(emp / acervo_ativo, 4) if acervo_ativo else 0.0
        resultado.append(OcupacaoArea(
            area_conhecimento=area, total_exemplares=total, emprestados=emp, reservados=res,
            disponiveis=disp, em_reparo=rep, baixados=baix, taxa_ocupacao=taxa,
        ))
    return resultado
