from datetime import datetime
from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models import Emprestimo, Exemplar, Livro, Usuario
from app.models.enums import EstadoExemplar, EstadoEmprestimo
from app.schemas.relatorio import (
    LivroMaisEmprestadoResponse,
    UsuarioMaisAtrasosResponse,
    TaxaOcupacaoAcervoResponse,
)
from app.utils import get_utcnow


def get_livros_mais_emprestados(
    db: Session,
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
    limite: int = 10
) -> List[LivroMaisEmprestadoResponse]:
    query = (
        db.query(
            Livro.id.label("livro_id"),
            Livro.titulo,
            Livro.autor,
            Livro.isbn,
            func.count(Emprestimo.id).label("total_emprestimos")
        )
        .join(Exemplar, Exemplar.livro_id == Livro.id)
        .join(Emprestimo, Emprestimo.exemplar_id == Exemplar.id)
    )

    if data_inicio:
        query = query.filter(Emprestimo.data_retirada >= data_inicio)
    if data_fim:
        query = query.filter(Emprestimo.data_retirada <= data_fim)

    resultados = (
        query.group_by(Livro.id, Livro.titulo, Livro.autor, Livro.isbn)
        .order_by(func.count(Emprestimo.id).desc())
        .limit(limite)
        .all()
    )

    return [
        LivroMaisEmprestadoResponse(
            livro_id=r.livro_id,
            titulo=r.titulo,
            autor=r.autor,
            isbn=r.isbn,
            total_emprestimos=r.total_emprestimos,
        )
        for r in resultados
    ]


def get_usuarios_mais_atrasos(
    db: Session,
    limite: int = 10
) -> List[UsuarioMaisAtrasosResponse]:
    usuarios = db.query(Usuario).all()
    agregados = []
    now = get_utcnow()

    for u in usuarios:
        total_atrasos = 0
        total_dias = 0

        for emp in u.emprestimos:
            data_fim_comparacao = emp.data_devolucao or now
            if data_fim_comparacao > emp.data_prevista:
                dias = (data_fim_comparacao.date() - emp.data_prevista.date()).days
                if dias > 0:
                    total_atrasos += 1
                    total_dias += dias

        if total_atrasos > 0:
            agregados.append(
                UsuarioMaisAtrasosResponse(
                    usuario_id=u.id,
                    nome=u.nome,
                    matricula=u.matricula,
                    categoria=u.categoria,
                    total_atrasos=total_atrasos,
                    total_dias_atraso=total_dias,
                )
            )

    agregados.sort(key=lambda x: (x.total_atrasos, x.total_dias_atraso), reverse=True)
    return agregados[:limite]


def get_taxa_ocupacao_acervo(db: Session) -> List[TaxaOcupacaoAcervoResponse]:
    areas = db.query(Livro.area).distinct().all()
    resultado = []

    for (area_nome,) in areas:
        exemplares = (
            db.query(Exemplar)
            .join(Livro, Livro.id == Exemplar.livro_id)
            .filter(Livro.area == area_nome)
            .all()
        )

        # Consideramos o acervo ativo (excluindo baixados para cálculo da taxa de ocupação física)
        total_exemplares = len(exemplares)
        emprestados = sum(1 for e in exemplares if e.estado == EstadoExemplar.EMPRESTADO)
        disponiveis = sum(1 for e in exemplares if e.estado == EstadoExemplar.DISPONIVEL)

        taxa = round((emprestados / total_exemplares * 100), 2) if total_exemplares > 0 else 0.0

        resultado.append(
            TaxaOcupacaoAcervoResponse(
                area=area_nome,
                total_exemplares=total_exemplares,
                exemplares_emprestados=emprestados,
                exemplares_disponiveis=disponiveis,
                taxa_ocupacao_percentual=taxa,
            )
        )

    resultado.sort(key=lambda x: x.taxa_ocupacao_percentual, reverse=True)
    return resultado
