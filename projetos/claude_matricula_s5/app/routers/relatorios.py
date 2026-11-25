from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..enums import EstadoMatricula as E
from ..enums import EstadoTurma, SituacaoHistorico as S
from ..models import Disciplina, Historico, Matricula, Turma
from ..schemas import (
    SEMESTRE_PATTERN,
    DisciplinaProcuradaOut,
    OcupacaoDepartamentoOut,
    OcupacaoTurmaOut,
    TaxaReprovacaoOut,
)

router = APIRouter(prefix="/relatorios", tags=["Relatorios"])


def _soma_se(condicao):
    return func.coalesce(func.sum(case((condicao, 1), else_=0)), 0)


@router.get("/disciplinas-mais-procuradas", response_model=list[DisciplinaProcuradaOut])
def disciplinas_mais_procuradas(
    semestre: str = Query(pattern=SEMESTRE_PATTERN),
    limite: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Ranking pelo total de solicitacoes de matricula (todas as turmas e estados) no semestre."""
    total = func.count(Matricula.id).label("total")
    linhas = db.execute(
        select(
            Disciplina.id,
            Disciplina.codigo,
            Disciplina.nome,
            Disciplina.departamento,
            total,
            _soma_se(Matricula.estado == E.CONFIRMADA).label("confirmadas"),
            _soma_se(Matricula.estado == E.LISTA_DE_ESPERA).label("espera"),
        )
        .join(Turma, Turma.disciplina_id == Disciplina.id)
        .join(Matricula, Matricula.turma_id == Turma.id)
        .where(Turma.semestre == semestre)
        .group_by(Disciplina.id, Disciplina.codigo, Disciplina.nome, Disciplina.departamento)
        .order_by(total.desc(), Disciplina.codigo)
        .limit(limite)
    ).all()
    return [
        DisciplinaProcuradaOut(
            disciplina_id=l.id,
            codigo=l.codigo,
            nome=l.nome,
            departamento=l.departamento,
            total_solicitacoes=l.total,
            confirmadas=l.confirmadas,
            lista_de_espera=l.espera,
        )
        for l in linhas
    ]


@router.get("/taxa-reprovacao", response_model=list[TaxaReprovacaoOut])
def taxa_reprovacao(
    semestre: str | None = Query(None, pattern=SEMESTRE_PATTERN),
    departamento: str | None = None,
    db: Session = Depends(get_db),
):
    """Taxa = reprovados / (aprovados + reprovados), com base no historico.

    Inclui reprovacoes por falta; trancamentos sao informados mas nao entram no calculo.
    """
    q = (
        select(
            Disciplina.id,
            Disciplina.codigo,
            Disciplina.nome,
            _soma_se(Historico.situacao == S.APROVADO).label("aprovados"),
            _soma_se(Historico.situacao == S.REPROVADO).label("reprovados"),
            _soma_se(Historico.situacao == S.TRANCADO).label("trancados"),
        )
        .join(Historico, Historico.disciplina_id == Disciplina.id)
        .group_by(Disciplina.id, Disciplina.codigo, Disciplina.nome)
    )
    if semestre:
        q = q.where(Historico.semestre == semestre)
    if departamento:
        q = q.where(Disciplina.departamento == departamento)
    resultado = []
    for l in db.execute(q).all():
        avaliados = l.aprovados + l.reprovados
        resultado.append(
            TaxaReprovacaoOut(
                disciplina_id=l.id,
                codigo=l.codigo,
                nome=l.nome,
                aprovados=l.aprovados,
                reprovados=l.reprovados,
                trancados=l.trancados,
                taxa_reprovacao=round(l.reprovados / avaliados, 4) if avaliados else None,
            )
        )
    resultado.sort(key=lambda r: (r.taxa_reprovacao is None, -(r.taxa_reprovacao or 0), r.codigo))
    return resultado


@router.get("/ocupacao-turmas", response_model=list[OcupacaoDepartamentoOut])
def ocupacao_turmas(
    semestre: str = Query(pattern=SEMESTRE_PATTERN),
    departamento: str | None = None,
    db: Session = Depends(get_db),
):
    """Ocupacao (solicitadas + confirmadas / vagas) das turmas nao canceladas, por departamento."""
    q = (
        select(
            Turma.id,
            Turma.vagas,
            Turma.estado,
            Disciplina.codigo,
            Disciplina.departamento,
            _soma_se(Matricula.estado == E.CONFIRMADA).label("confirmadas"),
            _soma_se(Matricula.estado.in_((E.SOLICITADA, E.CONFIRMADA))).label("ocupadas"),
            _soma_se(Matricula.estado == E.LISTA_DE_ESPERA).label("espera"),
        )
        .join(Disciplina, Turma.disciplina_id == Disciplina.id)
        .outerjoin(Matricula, Matricula.turma_id == Turma.id)
        .where(Turma.semestre == semestre, Turma.estado != EstadoTurma.CANCELADA)
        .group_by(Turma.id, Turma.vagas, Turma.estado, Disciplina.codigo, Disciplina.departamento)
        .order_by(Disciplina.departamento, Turma.id)
    )
    if departamento:
        q = q.where(Disciplina.departamento == departamento)

    grupos: dict[str, list[OcupacaoTurmaOut]] = defaultdict(list)
    for l in db.execute(q).all():
        grupos[l.departamento].append(
            OcupacaoTurmaOut(
                turma_id=l.id,
                disciplina_codigo=l.codigo,
                estado=l.estado,
                vagas=l.vagas,
                confirmadas=l.confirmadas,
                vagas_ocupadas=l.ocupadas,
                lista_de_espera=l.espera,
                taxa_ocupacao=round(l.ocupadas / l.vagas, 4),
            )
        )
    resultado = []
    for dep, turmas in sorted(grupos.items()):
        vagas = sum(t.vagas for t in turmas)
        ocupadas = sum(t.vagas_ocupadas for t in turmas)
        resultado.append(
            OcupacaoDepartamentoOut(
                departamento=dep,
                total_turmas=len(turmas),
                total_vagas=vagas,
                total_ocupadas=ocupadas,
                taxa_ocupacao=round(ocupadas / vagas, 4) if vagas else 0.0,
                turmas=turmas,
            )
        )
    return resultado
