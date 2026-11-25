from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app import services
from app.database import get_db
from app.enums import EstadoMatricula as EM
from app.enums import EstadoTurma, SituacaoHistorico
from app.models import Disciplina, Historico, Matricula, Turma

router = APIRouter(prefix="/relatorios", tags=["relatorios"])

SEMESTRE = r"^\d{4}\.[12]$"


@router.get("/disciplinas-mais-procuradas")
def disciplinas_mais_procuradas(semestre: str = Query(pattern=SEMESTRE), limite: int = Query(10, ge=1, le=100),
                                db: Session = Depends(get_db)):
    """Procura = total de solicitacoes de matricula (qualquer estado) nas turmas do semestre."""
    q = (
        select(
            Disciplina.id, Disciplina.codigo, Disciplina.nome, Disciplina.departamento,
            func.count(Matricula.id).label("solicitacoes"),
            func.sum(case((Matricula.estado == EM.CONFIRMADA, 1), else_=0)).label("confirmadas"),
            func.sum(case((Matricula.estado == EM.LISTA_DE_ESPERA, 1), else_=0)).label("lista_espera"),
        )
        .join(Turma, Turma.disciplina_id == Disciplina.id)
        .join(Matricula, Matricula.turma_id == Turma.id)
        .where(Turma.semestre == semestre)
        .group_by(Disciplina.id)
        .order_by(func.count(Matricula.id).desc(), Disciplina.codigo)
        .limit(limite)
    )
    return {
        "semestre": semestre,
        "disciplinas": [
            {"disciplina_id": r.id, "codigo": r.codigo, "nome": r.nome, "departamento": r.departamento,
             "solicitacoes": r.solicitacoes, "confirmadas": r.confirmadas or 0, "lista_espera": r.lista_espera or 0}
            for r in db.execute(q)
        ],
    }


@router.get("/taxa-reprovacao")
def taxa_reprovacao(semestre: str | None = Query(None, pattern=SEMESTRE), db: Session = Depends(get_db)):
    """Taxa = reprovados / (aprovados + reprovados), com base no historico. Trancamentos nao entram."""
    aprov = func.sum(case((Historico.situacao == SituacaoHistorico.APROVADO, 1), else_=0))
    reprov = func.sum(case((Historico.situacao == SituacaoHistorico.REPROVADO, 1), else_=0))
    q = (
        select(Disciplina.id, Disciplina.codigo, Disciplina.nome, Disciplina.departamento,
               aprov.label("aprovados"), reprov.label("reprovados"))
        .join(Historico, Historico.disciplina_id == Disciplina.id)
        .where(Historico.situacao.in_((SituacaoHistorico.APROVADO, SituacaoHistorico.REPROVADO)))
        .group_by(Disciplina.id)
    )
    if semestre:
        q = q.where(Historico.semestre == semestre)
    linhas = []
    for r in db.execute(q):
        total = r.aprovados + r.reprovados
        linhas.append({
            "disciplina_id": r.id, "codigo": r.codigo, "nome": r.nome, "departamento": r.departamento,
            "aprovados": r.aprovados, "reprovados": r.reprovados, "total_avaliados": total,
            "taxa_reprovacao": round(r.reprovados / total, 4) if total else 0.0,
        })
    linhas.sort(key=lambda x: (-x["taxa_reprovacao"], x["codigo"]))
    return {"semestre": semestre, "disciplinas": linhas}


@router.get("/ocupacao-turmas")
def ocupacao_turmas(semestre: str | None = Query(None, pattern=SEMESTRE), departamento: str | None = None,
                    incluir_canceladas: bool = False, db: Session = Depends(get_db)):
    """Ocupacao = vagas ocupadas (solicitadas + confirmadas) / vagas, agrupada por departamento."""
    services.processar_prazos(db)
    db.commit()
    q = select(Turma).join(Disciplina).order_by(Disciplina.departamento, Turma.id)
    if semestre:
        q = q.where(Turma.semestre == semestre)
    if departamento:
        q = q.where(Disciplina.departamento == departamento)
    if not incluir_canceladas:
        q = q.where(Turma.estado != EstadoTurma.CANCELADA)

    deptos: dict[str, dict] = {}
    for t in db.scalars(q):
        d = deptos.setdefault(t.disciplina.departamento, {
            "departamento": t.disciplina.departamento, "total_vagas": 0, "vagas_ocupadas": 0,
            "confirmadas": 0, "lista_espera": 0, "turmas": []})
        ocupadas = t.vagas_ocupadas
        d["total_vagas"] += t.vagas
        d["vagas_ocupadas"] += ocupadas
        d["confirmadas"] += t.confirmadas
        d["lista_espera"] += t.tamanho_lista_espera
        d["turmas"].append({
            "turma_id": t.id, "disciplina_codigo": t.disciplina.codigo, "semestre": t.semestre,
            "estado": t.estado.value, "vagas": t.vagas, "vagas_ocupadas": ocupadas,
            "confirmadas": t.confirmadas, "lista_espera": t.tamanho_lista_espera,
            "taxa_ocupacao": round(ocupadas / t.vagas, 4),
        })
    for d in deptos.values():
        d["taxa_ocupacao"] = round(d["vagas_ocupadas"] / d["total_vagas"], 4) if d["total_vagas"] else 0.0
    return {"semestre": semestre, "departamentos": list(deptos.values())}
