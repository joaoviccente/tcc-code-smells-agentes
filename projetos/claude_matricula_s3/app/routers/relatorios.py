from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..deps import db_sincronizado
from ..models import (
    Disciplina,
    EstadoMatricula,
    EstadoTurma,
    Historico,
    Matricula,
    SituacaoHistorico,
    Turma,
)

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])
E = EstadoMatricula


def _soma_se(cond):
    return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)


@router.get("/disciplinas-mais-procuradas")
def disciplinas_mais_procuradas(
    semestre: str = Query(pattern=schemas.SEMESTRE_REGEX),
    limite: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(db_sincronizado),
):
    """Procura = total de solicitações de matrícula (em qualquer estado) no semestre."""
    total = func.count(Matricula.id).label("total")
    linhas = db.execute(
        select(
            Disciplina.id,
            Disciplina.codigo,
            Disciplina.nome,
            Disciplina.departamento,
            total,
            _soma_se(Matricula.estado == E.confirmada).label("confirmadas"),
            _soma_se(Matricula.estado == E.lista_de_espera).label("em_espera"),
            func.count(func.distinct(Turma.id)).label("turmas"),
        )
        .select_from(Matricula)
        .join(Turma, Matricula.turma_id == Turma.id)
        .join(Disciplina, Turma.disciplina_id == Disciplina.id)
        .where(Turma.semestre == semestre)
        .group_by(Disciplina.id)
        .order_by(total.desc(), Disciplina.codigo)
        .limit(limite)
    ).all()
    return {
        "semestre": semestre,
        "disciplinas": [
            {
                "disciplina_id": r.id,
                "codigo": r.codigo,
                "nome": r.nome,
                "departamento": r.departamento,
                "total_solicitacoes": r.total,
                "confirmadas": r.confirmadas,
                "em_lista_de_espera": r.em_espera,
                "turmas": r.turmas,
            }
            for r in linhas
        ],
    }


@router.get("/taxa-reprovacao")
def taxa_reprovacao(
    semestre: Optional[str] = Query(default=None, pattern=schemas.SEMESTRE_REGEX),
    departamento: Optional[str] = None,
    db: Session = Depends(db_sincronizado),
):
    """Taxa = reprovados / (aprovados + reprovados). Trancamentos não entram no cálculo."""
    S = SituacaoHistorico
    aprov = _soma_se(Historico.situacao == S.aprovado).label("aprovados")
    reprov = _soma_se(Historico.situacao == S.reprovado).label("reprovados")
    tranc = _soma_se(Historico.situacao == S.trancado).label("trancados")
    q = (
        select(Disciplina.id, Disciplina.codigo, Disciplina.nome, Disciplina.departamento, aprov, reprov, tranc)
        .select_from(Historico)
        .join(Disciplina, Historico.disciplina_id == Disciplina.id)
        .group_by(Disciplina.id)
    )
    if semestre:
        q = q.where(Historico.semestre == semestre)
    if departamento:
        q = q.where(Disciplina.departamento == departamento)
    itens = []
    for r in db.execute(q).all():
        avaliados = r.aprovados + r.reprovados
        itens.append(
            {
                "disciplina_id": r.id,
                "codigo": r.codigo,
                "nome": r.nome,
                "departamento": r.departamento,
                "aprovados": r.aprovados,
                "reprovados": r.reprovados,
                "trancados": r.trancados,
                "taxa_reprovacao": round(r.reprovados / avaliados, 4) if avaliados else None,
            }
        )
    itens.sort(key=lambda i: (-(i["taxa_reprovacao"] or 0), i["codigo"]))
    return {"semestre": semestre, "disciplinas": itens}


@router.get("/ocupacao-turmas")
def ocupacao_turmas_por_departamento(
    semestre: str = Query(pattern=schemas.SEMESTRE_REGEX),
    db: Session = Depends(db_sincronizado),
):
    """Ocupação = matrículas confirmadas / vagas ofertadas (turmas canceladas excluídas)."""
    confirmadas = (
        select(func.count(Matricula.id))
        .where(Matricula.turma_id == Turma.id, Matricula.estado == E.confirmada)
        .correlate(Turma)
        .scalar_subquery()
    )
    em_espera = (
        select(func.count(Matricula.id))
        .where(Matricula.turma_id == Turma.id, Matricula.estado == E.lista_de_espera)
        .correlate(Turma)
        .scalar_subquery()
    )
    linhas = db.execute(
        select(
            Turma.id,
            Turma.vagas,
            Turma.estado,
            Disciplina.codigo,
            Disciplina.departamento,
            confirmadas.label("confirmadas"),
            em_espera.label("em_espera"),
        )
        .join(Disciplina, Turma.disciplina_id == Disciplina.id)
        .where(Turma.semestre == semestre, Turma.estado != EstadoTurma.cancelada)
        .order_by(Disciplina.departamento, Disciplina.codigo, Turma.id)
    ).all()

    deps: dict[str, dict] = {}
    for r in linhas:
        d = deps.setdefault(
            r.departamento,
            {"departamento": r.departamento, "turmas": 0, "vagas": 0, "confirmadas": 0,
             "em_lista_de_espera": 0, "detalhes": []},
        )
        d["turmas"] += 1
        d["vagas"] += r.vagas
        d["confirmadas"] += r.confirmadas
        d["em_lista_de_espera"] += r.em_espera
        d["detalhes"].append(
            {
                "turma_id": r.id,
                "disciplina": r.codigo,
                "estado": r.estado.value,
                "vagas": r.vagas,
                "confirmadas": r.confirmadas,
                "em_lista_de_espera": r.em_espera,
                "taxa_ocupacao": round(r.confirmadas / r.vagas, 4),
            }
        )
    for d in deps.values():
        d["taxa_ocupacao"] = round(d["confirmadas"] / d["vagas"], 4) if d["vagas"] else 0.0
    return {"semestre": semestre, "departamentos": list(deps.values())}
