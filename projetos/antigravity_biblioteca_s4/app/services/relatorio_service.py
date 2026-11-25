from datetime import datetime
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, case
from app.models.livro import Livro
from app.models.exemplar import Exemplar
from app.models.emprestimo import Emprestimo
from app.models.usuario import Usuario
from app.models.enums import EstadoExemplar, EstadoEmprestimo
from app.schemas.relatorio import (
    LivroMaisEmprestado,
    UsuarioMaisAtrasos,
    TaxaOcupacaoArea,
)


def relatorio_livros_mais_emprestados(
    db: Session, data_inicio: datetime, data_fim: datetime
) -> List[LivroMaisEmprestado]:
    """Relatório de livros mais emprestados em um período (por data de retirada)."""
    # Ajuste: se data_fim vier apenas data ou meia-noite, certificar que abrange o dia todo se aplicável
    results = (
        db.query(
            Livro.id.label("livro_id"),
            Livro.titulo.label("titulo"),
            Livro.autor.label("autor"),
            Livro.isbn.label("isbn"),
            func.count(Emprestimo.id).label("total_emprestimos"),
        )
        .join(Exemplar, Exemplar.livro_id == Livro.id)
        .join(Emprestimo, Emprestimo.exemplar_id == Exemplar.id)
        .filter(
            Emprestimo.data_retirada >= data_inicio,
            Emprestimo.data_retirada <= data_fim,
        )
        .group_by(Livro.id, Livro.titulo, Livro.autor, Livro.isbn)
        .order_by(func.count(Emprestimo.id).desc(), Livro.titulo.asc())
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
        for r in results
    ]


def relatorio_usuarios_mais_atrasos(db: Session) -> List[UsuarioMaisAtrasos]:
    """Relatório de usuários com mais atrasos (devolvidos com atraso ou atualmente atrasados)."""
    agora = datetime.now()
    results = (
        db.query(
            Usuario.id.label("usuario_id"),
            Usuario.nome.label("nome"),
            Usuario.matricula.label("matricula"),
            Usuario.categoria.label("categoria"),
            func.count(Emprestimo.id).label("total_atrasos"),
        )
        .join(Emprestimo, Emprestimo.usuario_id == Usuario.id)
        .filter(
            or_(
                # Devolvido após a data prevista
                Emprestimo.data_devolucao > Emprestimo.data_prevista,
                # Ou ainda não devolvido e com data prevista vencida
                (Emprestimo.data_devolucao.is_(None)) & (Emprestimo.data_prevista < agora),
                Emprestimo.estado == EstadoEmprestimo.ATRASADO,
            )
        )
        .group_by(Usuario.id, Usuario.nome, Usuario.matricula, Usuario.categoria)
        .order_by(func.count(Emprestimo.id).desc(), Usuario.nome.asc())
        .all()
    )

    return [
        UsuarioMaisAtrasos(
            usuario_id=r.usuario_id,
            nome=r.nome,
            matricula=r.matricula,
            categoria=r.categoria,
            total_atrasos=r.total_atrasos,
        )
        for r in results
    ]


def relatorio_taxa_ocupacao_acervo(db: Session) -> List[TaxaOcupacaoArea]:
    """
    Taxa de ocupação do acervo por área de conhecimento.
    Considera o acervo ativo (não baixado) e calcula a proporção de exemplares emprestados.
    """
    areas = (
        db.query(Livro.area_conhecimento)
        .distinct()
        .order_by(Livro.area_conhecimento.asc())
        .all()
    )

    relatorio = []
    for (area,) in areas:
        total_exemplares = (
            db.query(func.count(Exemplar.id))
            .join(Livro, Livro.id == Exemplar.livro_id)
            .filter(
                Livro.area_conhecimento == area,
                Exemplar.estado != EstadoExemplar.BAIXADO,
            )
            .scalar()
        ) or 0

        exemplares_emprestados = (
            db.query(func.count(Exemplar.id))
            .join(Livro, Livro.id == Exemplar.livro_id)
            .filter(
                Livro.area_conhecimento == area,
                Exemplar.estado == EstadoExemplar.EMPRESTADO,
            )
            .scalar()
        ) or 0

        taxa = (
            round((exemplares_emprestados / total_exemplares) * 100, 2)
            if total_exemplares > 0
            else 0.0
        )

        relatorio.append(
            TaxaOcupacaoArea(
                area_conhecimento=area,
                total_exemplares=total_exemplares,
                exemplares_emprestados=exemplares_emprestados,
                taxa_ocupacao_percentual=taxa,
            )
        )

    return relatorio
