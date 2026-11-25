from collections import defaultdict
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..enums import EstadoEmprestimo, EstadoExemplar
from ..models import Emprestimo, Exemplar, Livro, Usuario
from ..schemas import LivroMaisEmprestado, OcupacaoArea, UsuarioComAtrasos
from ..servicos import ErroNegocio

router = APIRouter(prefix="/relatorios", tags=["relatorios"])


def _intervalo(inicio: date | None, fim: date | None) -> tuple[datetime | None, datetime | None]:
    if inicio and fim and inicio > fim:
        raise ErroNegocio("data_inicio deve ser anterior ou igual a data_fim", 422)
    return (datetime.combine(inicio, time.min) if inicio else None,
            datetime.combine(fim + timedelta(days=1), time.min) if fim else None)


@router.get("/livros-mais-emprestados", response_model=list[LivroMaisEmprestado])
def livros_mais_emprestados(data_inicio: date = Query(..., description="AAAA-MM-DD (inclusive)"),
                            data_fim: date = Query(..., description="AAAA-MM-DD (inclusive)"),
                            limite: int = Query(10, ge=1, le=100),
                            db: Session = Depends(get_db)):
    """Livros com mais emprestimos retirados no periodo."""
    ini, fim = _intervalo(data_inicio, data_fim)
    total = func.count(Emprestimo.id).label("total")
    q = (select(Livro.id, Livro.titulo, Livro.autor, Livro.isbn, total)
         .join(Exemplar, Exemplar.livro_id == Livro.id)
         .join(Emprestimo, Emprestimo.exemplar_id == Exemplar.id)
         .where(Emprestimo.data_retirada >= ini, Emprestimo.data_retirada < fim)
         .group_by(Livro.id).order_by(total.desc(), Livro.titulo).limit(limite))
    return [LivroMaisEmprestado(livro_id=i, titulo=t, autor=a, isbn=isbn, total_emprestimos=n)
            for i, t, a, isbn, n in db.execute(q)]


@router.get("/usuarios-mais-atrasos", response_model=list[UsuarioComAtrasos])
def usuarios_com_mais_atrasos(data_inicio: date | None = Query(None, description="Filtra pela data de retirada"),
                              data_fim: date | None = Query(None),
                              limite: int = Query(10, ge=1, le=100),
                              db: Session = Depends(get_db)):
    """Usuarios com mais emprestimos em atraso (devolvidos com atraso ou atualmente atrasados)."""
    ini, fim = _intervalo(data_inicio, data_fim)
    q = select(Emprestimo).where(Emprestimo.estado != EstadoEmprestimo.ativo)
    if ini:
        q = q.where(Emprestimo.data_retirada >= ini)
    if fim:
        q = q.where(Emprestimo.data_retirada < fim)
    contagem: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for emp in db.scalars(q):
        dias = emp.dias_atraso
        if dias > 0:
            contagem[emp.usuario_id][0] += 1
            contagem[emp.usuario_id][1] += dias
    usuarios = {u.id: u for u in db.scalars(select(Usuario).where(Usuario.id.in_(contagem.keys())))}
    linhas = [UsuarioComAtrasos(usuario_id=uid, nome=usuarios[uid].nome, matricula=usuarios[uid].matricula,
                                categoria=usuarios[uid].categoria, quantidade_atrasos=n, total_dias_atraso=d)
              for uid, (n, d) in contagem.items()]
    linhas.sort(key=lambda l: (-l.quantidade_atrasos, -l.total_dias_atraso, l.usuario_id))
    return linhas[:limite]


@router.get("/ocupacao-acervo", response_model=list[OcupacaoArea])
def ocupacao_por_area(db: Session = Depends(get_db)):
    """Taxa de ocupacao do acervo por area: exemplares emprestados / exemplares no acervo (nao baixados)."""
    q = (select(Livro.area_conhecimento, Exemplar.estado, func.count(Exemplar.id))
         .join(Exemplar, Exemplar.livro_id == Livro.id)
         .group_by(Livro.area_conhecimento, Exemplar.estado))
    por_area: dict[str, dict[EstadoExemplar, int]] = defaultdict(lambda: defaultdict(int))
    for area, estado, n in db.execute(q):
        por_area[area][EstadoExemplar(estado)] += n
    resultado = []
    for area in sorted(por_area):
        c = por_area[area]
        total = sum(n for e, n in c.items() if e != EstadoExemplar.baixado)
        emprestados = c[EstadoExemplar.emprestado]
        resultado.append(OcupacaoArea(
            area_conhecimento=area, total_exemplares=total, emprestados=emprestados,
            reservados=c[EstadoExemplar.reservado], disponiveis=c[EstadoExemplar.disponivel],
            em_reparo=c[EstadoExemplar.em_reparo], baixados=c[EstadoExemplar.baixado],
            taxa_ocupacao=round(emprestados / total * 100, 2) if total else 0.0,
        ))
    return resultado
