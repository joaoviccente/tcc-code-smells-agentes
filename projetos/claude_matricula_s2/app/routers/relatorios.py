from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Disciplina, EstadoMatricula as EM, EstadoTurma as ET, Historico, Matricula, SituacaoHistorico as SH, Turma,
)
from app.schemas import Semestre

router = APIRouter(prefix="/relatorios", tags=["Relatorios"])


class DisciplinaProcurada(BaseModel):
    disciplina_id: int
    codigo: str
    nome: str
    departamento: str
    total_solicitacoes: int
    confirmadas: int
    em_lista_de_espera: int


class TaxaReprovacao(BaseModel):
    disciplina_id: int
    codigo: str
    nome: str
    aprovados: int
    reprovados: int
    total_avaliados: int
    taxa_reprovacao: float


class OcupacaoTurma(BaseModel):
    turma_id: int
    disciplina_codigo: str
    semestre: str
    estado: ET
    vagas: int
    confirmadas: int
    taxa_ocupacao: float


class OcupacaoDepartamento(BaseModel):
    departamento: str
    total_turmas: int
    total_vagas: int
    total_confirmadas: int
    taxa_ocupacao: float
    turmas: list[OcupacaoTurma]


@router.get("/disciplinas-mais-procuradas", response_model=list[DisciplinaProcurada])
def disciplinas_mais_procuradas(
    semestre: Semestre, limite: int = Query(10, ge=1, le=100), db: Session = Depends(get_db),
):
    """Ranking por numero de solicitacoes de matricula (qualquer estado) nas turmas do semestre."""
    total = func.count(Matricula.id)
    q = (
        select(
            Disciplina.id, Disciplina.codigo, Disciplina.nome, Disciplina.departamento, total,
            func.sum(case((Matricula.estado == EM.CONFIRMADA, 1), else_=0)),
            func.sum(case((Matricula.estado == EM.LISTA_DE_ESPERA, 1), else_=0)),
        )
        .select_from(Matricula)
        .join(Turma, Matricula.turma_id == Turma.id)
        .join(Disciplina, Turma.disciplina_id == Disciplina.id)
        .where(Turma.semestre == semestre)
        .group_by(Disciplina.id)
        .order_by(total.desc(), Disciplina.codigo)
        .limit(limite)
    )
    return [
        DisciplinaProcurada(disciplina_id=r[0], codigo=r[1], nome=r[2], departamento=r[3],
                            total_solicitacoes=r[4], confirmadas=r[5] or 0, em_lista_de_espera=r[6] or 0)
        for r in db.execute(q).all()
    ]


@router.get("/taxa-reprovacao", response_model=list[TaxaReprovacao])
def taxa_reprovacao(
    semestre: Semestre | None = None, departamento: str | None = None, db: Session = Depends(get_db),
):
    """Reprovados / (aprovados + reprovados) segundo o historico. Trancamentos nao entram no calculo."""
    aprov = func.sum(case((Historico.situacao == SH.APROVADO, 1), else_=0))
    reprov = func.sum(case((Historico.situacao == SH.REPROVADO, 1), else_=0))
    q = (
        select(Disciplina.id, Disciplina.codigo, Disciplina.nome, aprov, reprov)
        .select_from(Historico)
        .join(Disciplina, Historico.disciplina_id == Disciplina.id)
        .where(Historico.situacao.in_([SH.APROVADO, SH.REPROVADO]))
        .group_by(Disciplina.id)
    )
    if semestre:
        q = q.where(Historico.semestre == semestre)
    if departamento:
        q = q.where(Disciplina.departamento == departamento)
    linhas = []
    for r in db.execute(q).all():
        a, rp = r[3] or 0, r[4] or 0
        linhas.append(TaxaReprovacao(
            disciplina_id=r[0], codigo=r[1], nome=r[2], aprovados=a, reprovados=rp, total_avaliados=a + rp,
            taxa_reprovacao=round(rp / (a + rp), 4) if a + rp else 0.0,
        ))
    return sorted(linhas, key=lambda x: (-x.taxa_reprovacao, x.codigo))


@router.get("/ocupacao-turmas", response_model=list[OcupacaoDepartamento])
def ocupacao_turmas(
    semestre: Semestre | None = None, departamento: str | None = None, db: Session = Depends(get_db),
):
    """Ocupacao (matriculas confirmadas / vagas) das turmas nao canceladas, agrupada por departamento."""
    confirmadas = func.sum(case((Matricula.estado == EM.CONFIRMADA, 1), else_=0))
    q = (
        select(Turma.id, Disciplina.codigo, Disciplina.departamento, Turma.semestre, Turma.estado, Turma.vagas,
               func.coalesce(confirmadas, 0))
        .select_from(Turma)
        .join(Disciplina, Turma.disciplina_id == Disciplina.id)
        .outerjoin(Matricula, Matricula.turma_id == Turma.id)
        .where(Turma.estado != ET.CANCELADA)
        .group_by(Turma.id)
        .order_by(Disciplina.departamento, Turma.id)
    )
    if semestre:
        q = q.where(Turma.semestre == semestre)
    if departamento:
        q = q.where(Disciplina.departamento == departamento)

    grupos: dict[str, list[OcupacaoTurma]] = defaultdict(list)
    for tid, cod, dep, sem, est, vagas, conf in db.execute(q).all():
        grupos[dep].append(OcupacaoTurma(
            turma_id=tid, disciplina_codigo=cod, semestre=sem, estado=est, vagas=vagas,
            confirmadas=conf, taxa_ocupacao=round(conf / vagas, 4),
        ))
    saida = []
    for dep, turmas in sorted(grupos.items()):
        tv = sum(t.vagas for t in turmas)
        tc = sum(t.confirmadas for t in turmas)
        saida.append(OcupacaoDepartamento(
            departamento=dep, total_turmas=len(turmas), total_vagas=tv, total_confirmadas=tc,
            taxa_ocupacao=round(tc / tv, 4) if tv else 0.0, turmas=turmas,
        ))
    return saida
