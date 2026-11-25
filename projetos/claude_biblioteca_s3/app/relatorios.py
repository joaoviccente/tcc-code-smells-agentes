"""Consultas dos relatorios gerenciais."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.enums import EstadoEmprestimo, EstadoExemplar
from app.models import Emprestimo, Exemplar, Livro, Usuario
from app.schemas import LivroMaisEmprestado, OcupacaoArea, UsuarioAtrasos
from app.servicos import dias_atraso


def _intervalo(inicio: date | None, fim: date | None) -> tuple[datetime | None, datetime | None]:
    ini = datetime.combine(inicio, time.min) if inicio else None
    # fim inclusivo: tudo antes do inicio do dia seguinte
    fim_excl = datetime.combine(fim + timedelta(days=1), time.min) if fim else None
    return ini, fim_excl


def livros_mais_emprestados(db: Session, inicio: date, fim: date, limite: int) -> list[LivroMaisEmprestado]:
    ini, fim_excl = _intervalo(inicio, fim)
    total = func.count(Emprestimo.id).label("total")
    linhas = db.execute(
        select(Livro.id, Livro.titulo, Livro.autor, total)
        .join(Exemplar, Exemplar.livro_id == Livro.id)
        .join(Emprestimo, Emprestimo.exemplar_id == Exemplar.id)
        .where(Emprestimo.data_retirada >= ini, Emprestimo.data_retirada < fim_excl)
        .group_by(Livro.id, Livro.titulo, Livro.autor)
        .order_by(total.desc(), Livro.titulo)
        .limit(limite)
    ).all()
    return [LivroMaisEmprestado(livro_id=l.id, titulo=l.titulo, autor=l.autor, total_emprestimos=l.total)
            for l in linhas]


def usuarios_com_mais_atrasos(db: Session, inicio: date | None, fim: date | None,
                              limite: int) -> list[UsuarioAtrasos]:
    """Conta emprestimos atrasados (em curso) ou devolvidos apos a data prevista.

    O periodo, se informado, filtra pela data prevista de devolucao.
    """
    ini, fim_excl = _intervalo(inicio, fim)
    consulta = select(Emprestimo).where(
        (Emprestimo.estado == EstadoEmprestimo.ATRASADO)
        | ((Emprestimo.estado == EstadoEmprestimo.DEVOLVIDO)
           & (func.date(Emprestimo.data_devolucao) > func.date(Emprestimo.data_prevista)))
    )
    if ini:
        consulta = consulta.where(Emprestimo.data_prevista >= ini)
    if fim_excl:
        consulta = consulta.where(Emprestimo.data_prevista < fim_excl)

    agora = clock.agora()
    qtd: dict[int, int] = defaultdict(int)
    dias: dict[int, int] = defaultdict(int)
    for emp in db.scalars(consulta):
        d = dias_atraso(emp, agora)
        if d > 0:
            qtd[emp.usuario_id] += 1
            dias[emp.usuario_id] += d

    usuarios = {u.id: u for u in db.scalars(select(Usuario).where(Usuario.id.in_(qtd.keys())))}
    ordenados = sorted(qtd, key=lambda uid: (-qtd[uid], -dias[uid], uid))[:limite]
    return [UsuarioAtrasos(usuario_id=uid, nome=usuarios[uid].nome, matricula=usuarios[uid].matricula,
                           categoria=usuarios[uid].categoria, emprestimos_atrasados=qtd[uid],
                           total_dias_atraso=dias[uid]) for uid in ordenados]


def ocupacao_por_area(db: Session) -> list[OcupacaoArea]:
    """Taxa de ocupacao = exemplares emprestados / exemplares do acervo ativo (exclui baixados)."""
    linhas = db.execute(
        select(Livro.area, Exemplar.estado, func.count(Exemplar.id))
        .join(Exemplar, Exemplar.livro_id == Livro.id)
        .group_by(Livro.area, Exemplar.estado)
    ).all()
    por_area: dict[str, dict[EstadoExemplar, int]] = defaultdict(lambda: defaultdict(int))
    for area, estado, n in linhas:
        por_area[area][EstadoExemplar(estado)] += n

    resultado = []
    for area in sorted(por_area):
        c = por_area[area]
        acervo = sum(n for e, n in c.items() if e != EstadoExemplar.BAIXADO)
        emprestados = c[EstadoExemplar.EMPRESTADO]
        resultado.append(OcupacaoArea(
            area=area,
            total_exemplares=acervo,
            emprestados=emprestados,
            reservados=c[EstadoExemplar.RESERVADO],
            disponiveis=c[EstadoExemplar.DISPONIVEL],
            em_reparo=c[EstadoExemplar.EM_REPARO],
            baixados=c[EstadoExemplar.BAIXADO],
            taxa_ocupacao=round(emprestados / acervo, 4) if acervo else 0.0,
        ))
    return resultado
