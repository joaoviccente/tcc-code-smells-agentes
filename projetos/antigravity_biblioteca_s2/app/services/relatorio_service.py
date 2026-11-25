from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.emprestimo import Emprestimo
from app.models.enums import EstadoEmprestimo, EstadoExemplar
from app.models.exemplar import Exemplar
from app.models.livro import Livro
from app.models.usuario import Usuario
from app.schemas.relatorio import LivroMaisEmprestado, TaxaOcupacaoArea, UsuarioMaisAtrasos
from app.services.usuario_service import calcular_dias_atraso


def relatorio_livros_mais_emprestados(
    db: Session,
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
    limite: int = 10,
) -> List[LivroMaisEmprestado]:
    query = (
        db.query(
            Livro.id.label("livro_id"),
            Livro.titulo,
            Livro.autor,
            Livro.isbn,
            func.count(Emprestimo.id).label("total_emprestimos"),
        )
        .join(Exemplar, Livro.id == Exemplar.livro_id)
        .join(Emprestimo, Exemplar.id == Emprestimo.exemplar_id)
    )

    if data_inicio:
        if data_inicio.tzinfo is None:
            data_inicio = data_inicio.replace(tzinfo=timezone.utc)
        query = query.filter(Emprestimo.data_retirada >= data_inicio)

    if data_fim:
        if data_fim.tzinfo is None:
            data_fim = data_fim.replace(tzinfo=timezone.utc)
        query = query.filter(Emprestimo.data_retirada <= data_fim)

    resultados = (
        query.group_by(Livro.id, Livro.titulo, Livro.autor, Livro.isbn)
        .order_by(func.count(Emprestimo.id).desc())
        .limit(limite)
        .all()
    )

    return [
        LivroMaisEmprestado(
            livro_id=r.livro_id,
            titulo=r.titulo,
            autor=r.autor,
            isbn=r.isbn,
            total_emprestimos=r.total_emprestimos,
        )
        for r in resultados
    ]


def relatorio_usuarios_mais_atrasos(
    db: Session,
    limite: int = 10,
    data_referencia: Optional[datetime] = None,
) -> List[UsuarioMaisAtrasos]:
    if data_referencia is None:
        data_referencia = datetime.now(timezone.utc)
    elif data_referencia.tzinfo is None:
        data_referencia = data_referencia.replace(tzinfo=timezone.utc)

    # Buscar todos os empréstimos
    emprestimos = db.query(Emprestimo).join(Usuario, Emprestimo.usuario_id == Usuario.id).all()

    stats_por_usuario = {}

    for emp in emprestimos:
        user = emp.usuario
        prevista = (
            emp.data_prevista
            if emp.data_prevista.tzinfo
            else emp.data_prevista.replace(tzinfo=timezone.utc)
        )

        data_fim_calc = emp.data_devolucao if emp.data_devolucao else data_referencia
        if data_fim_calc.tzinfo is None:
            data_fim_calc = data_fim_calc.replace(tzinfo=timezone.utc)

        dias = calcular_dias_atraso(data_fim_calc, prevista)

        if user.id not in stats_por_usuario:
            stats_por_usuario[user.id] = {
                "usuario_id": user.id,
                "nome": user.nome,
                "matricula": user.matricula,
                "categoria": user.categoria,
                "total_atrasos": 0,
                "total_dias_atraso": 0,
            }

        if dias > 0:
            stats_por_usuario[user.id]["total_atrasos"] += 1
            stats_por_usuario[user.id]["total_dias_atraso"] += dias

    # Filtrar usuários que tiveram pelo menos 1 atraso ou ordenar todos
    usuarios_ordenados = sorted(
        stats_por_usuario.values(),
        key=lambda x: (x["total_atrasos"], x["total_dias_atraso"]),
        reverse=True,
    )

    return [UsuarioMaisAtrasos(**u) for u in usuarios_ordenados[:limite]]


def relatorio_taxa_ocupacao_por_area(db: Session) -> List[TaxaOcupacaoArea]:
    # Buscar todas as áreas distintas de conhecimento cadastradas
    areas = db.query(Livro.area_conhecimento).distinct().all()

    relatorio = []
    for (area,) in areas:
        # Contagem de exemplares da área
        # Total circulante (desconsiderando baixados) ou total geral
        total_exemplares = (
            db.query(Exemplar)
            .join(Livro, Exemplar.livro_id == Livro.id)
            .filter(
                Livro.area_conhecimento == area,
                Exemplar.estado != EstadoExemplar.BAIXADO,
            )
            .count()
        )

        exemplares_emprestados = (
            db.query(Exemplar)
            .join(Livro, Exemplar.livro_id == Livro.id)
            .filter(
                Livro.area_conhecimento == area,
                Exemplar.estado == EstadoExemplar.EMPRESTADO,
            )
            .count()
        )

        if total_exemplares > 0:
            taxa = round((exemplares_emprestados / total_exemplares) * 100, 2)
        else:
            taxa = 0.0

        relatorio.append(
            TaxaOcupacaoArea(
                area_conhecimento=area,
                total_exemplares=total_exemplares,
                exemplares_emprestados=exemplares_emprestados,
                taxa_ocupacao_percentual=taxa,
            )
        )

    # Ordenar por taxa de ocupação decrescente
    relatorio.sort(key=lambda x: x.taxa_ocupacao_percentual, reverse=True)
    return relatorio
