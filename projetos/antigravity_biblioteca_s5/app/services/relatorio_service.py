from datetime import datetime, timezone
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.config import EstadoEmprestimo, EstadoExemplar
from app.models.emprestimo import Emprestimo
from app.models.exemplar import Exemplar
from app.models.livro import Livro
from app.models.usuario import Usuario
from app.schemas.relatorio import (
    LivroMaisEmprestadoResponse,
    TaxaOcupacaoAreaResponse,
    UsuarioMaisAtrasosResponse,
)
from app.services.emprestimo_service import atualizar_emprestimos_atrasados


def relatorio_livros_mais_emprestados(
    db: Session,
    data_inicio: datetime,
    data_fim: datetime,
    limite: int = 10,
) -> list[LivroMaisEmprestadoResponse]:
    resultados = (
        db.query(
            Livro.id.label("livro_id"),
            Livro.titulo.label("titulo"),
            Livro.autor.label("autor"),
            Livro.area_conhecimento.label("area_conhecimento"),
            func.count(Emprestimo.id).label("total_emprestimos"),
        )
        .join(Exemplar, Exemplar.livro_id == Livro.id)
        .join(Emprestimo, Emprestimo.exemplar_id == Exemplar.id)
        .filter(
            Emprestimo.data_retirada >= data_inicio,
            Emprestimo.data_retirada <= data_fim,
        )
        .group_by(Livro.id, Livro.titulo, Livro.autor, Livro.area_conhecimento)
        .order_by(func.count(Emprestimo.id).desc())
        .limit(limite)
        .all()
    )

    return [
        LivroMaisEmprestadoResponse(
            livro_id=r.livro_id,
            titulo=r.titulo,
            autor=r.autor,
            area_conhecimento=r.area_conhecimento,
            total_emprestimos=r.total_emprestimos,
        )
        for r in resultados
    ]


def relatorio_usuarios_com_mais_atrasos(
    db: Session,
    limite: int = 10,
    now: datetime | None = None,
) -> list[UsuarioMaisAtrasosResponse]:
    if now is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
    atualizar_emprestimos_atrasados(db, now)

    # Identifica atrasos:
    # 1) Devolvido após a data prevista
    # 2) Empréstimo em aberto já vencido (data_prevista < now) ou estado ATRASADO
    condicao_atraso = case(
        (
            (Emprestimo.data_devolucao.isnot(None))
            & (Emprestimo.data_devolucao > Emprestimo.data_prevista),
            1,
        ),
        (
            (Emprestimo.data_devolucao.is_(None))
            & ((Emprestimo.data_prevista < now) | (Emprestimo.estado == EstadoEmprestimo.ATRASADO)),
            1,
        ),
        else_=0,
    )

    resultados = (
        db.query(
            Usuario.id.label("usuario_id"),
            Usuario.nome.label("nome"),
            Usuario.matricula.label("matricula"),
            Usuario.categoria.label("categoria"),
            func.sum(condicao_atraso).label("total_atrasos"),
        )
        .join(Emprestimo, Emprestimo.usuario_id == Usuario.id)
        .group_by(Usuario.id, Usuario.nome, Usuario.matricula, Usuario.categoria)
        .having(func.sum(condicao_atraso) > 0)
        .order_by(func.sum(condicao_atraso).desc())
        .limit(limite)
        .all()
    )

    return [
        UsuarioMaisAtrasosResponse(
            usuario_id=r.usuario_id,
            nome=r.nome,
            matricula=r.matricula,
            categoria=r.categoria.value,
            total_atrasos=int(r.total_atrasos or 0),
        )
        for r in resultados
    ]


def relatorio_taxa_ocupacao_por_area(db: Session) -> list[TaxaOcupacaoAreaResponse]:
    # Agrupa por área de conhecimento considerando exemplares ativos (não baixados)
    areas = db.query(Livro.area_conhecimento).distinct().all()

    relatorio = []
    for (area,) in areas:
        total_exemplares = (
            db.query(Exemplar)
            .join(Livro, Livro.id == Exemplar.livro_id)
            .filter(
                Livro.area_conhecimento == area,
                Exemplar.estado != EstadoExemplar.BAIXADO,
            )
            .count()
        )

        exemplares_emprestados = (
            db.query(Exemplar)
            .join(Livro, Livro.id == Exemplar.livro_id)
            .filter(
                Livro.area_conhecimento == area,
                Exemplar.estado == EstadoExemplar.EMPRESTADO,
            )
            .count()
        )

        taxa = 0.0
        if total_exemplares > 0:
            taxa = round((exemplares_emprestados / total_exemplares) * 100.0, 2)

        relatorio.append(
            TaxaOcupacaoAreaResponse(
                area_conhecimento=area,
                total_exemplares=total_exemplares,
                exemplares_emprestados=exemplares_emprestados,
                taxa_ocupacao_percentual=taxa,
            )
        )

    # Ordena por taxa de ocupação decrescente
    relatorio.sort(key=lambda x: x.taxa_ocupacao_percentual, reverse=True)
    return relatorio
