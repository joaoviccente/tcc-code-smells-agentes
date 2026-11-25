"""Historico (lancamento), operacoes de periodo letivo e relatorios."""
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app import servicos as sv
from app.database import get_db
from app.models import (Aluno, Disciplina, EstadoMatricula as EM, EstadoTurma as ET,
                        Historico, Matricula, SituacaoHistorico as SH, Turma)
from app.routers.comum import historico_saida
from app.schemas import HistoricoCriar, HistoricoSaida, Semestre

historico = APIRouter(prefix="/historico", tags=["Historico"])
periodos = APIRouter(tags=["Periodo letivo"])
relatorios = APIRouter(prefix="/relatorios", tags=["Relatorios"])


# ------------------------------------------------------------ historico
@historico.post("", response_model=HistoricoSaida, status_code=status.HTTP_201_CREATED,
                summary="Lancar resultado no historico do aluno")
def lancar(dados: HistoricoCriar, db: Session = Depends(get_db)):
    sv.obter(db, Aluno, dados.aluno_id, "Aluno")
    sv.obter(db, Disciplina, dados.disciplina_id, "Disciplina")
    h = Historico(**dados.model_dump())
    db.add(h)
    db.commit()
    return historico_saida(h)


# ------------------------------------------------------------ periodo
@periodos.post("/semestres/{semestre}/encerrar-periodo-matricula",
               summary="Encerra o periodo de matricula (cancela turmas com < 5 confirmadas)")
def encerrar_periodo(semestre: Semestre = Path(...), db: Session = Depends(get_db)):
    return sv.encerrar_periodo_matricula(db, semestre)


@periodos.post("/lista-espera/processar-expiracoes", tags=["Lista de espera"],
               summary="Cancela ofertas de vaga com prazo de 48h expirado")
def processar_expiracoes(db: Session = Depends(get_db)):
    return {"ofertas_expiradas": sv.processar_todas_expiracoes(db)}


# ------------------------------------------------------------ relatorios
@relatorios.get("/disciplinas-mais-procuradas")
def mais_procuradas(semestre: Semestre, limite: int = Query(10, ge=1, le=100),
                    db: Session = Depends(get_db)):
    """Procura = total de solicitacoes de matricula (qualquer estado) nas turmas
    da disciplina no semestre."""
    rows = db.execute(
        select(Disciplina.id, Disciplina.codigo, Disciplina.nome, Disciplina.departamento,
               func.count(Matricula.id).label("solicitacoes"),
               func.sum(case((Matricula.estado == EM.confirmada, 1), else_=0)),
               func.sum(case((Matricula.estado == EM.lista_de_espera, 1), else_=0)))
        .join(Turma, Turma.disciplina_id == Disciplina.id)
        .join(Matricula, Matricula.turma_id == Turma.id)
        .where(Turma.semestre == semestre)
        .group_by(Disciplina.id)
        .order_by(func.count(Matricula.id).desc(), Disciplina.codigo)
        .limit(limite)
    ).all()
    return {"semestre": semestre, "disciplinas": [
        {"disciplina_id": r[0], "codigo": r[1], "nome": r[2], "departamento": r[3],
         "total_solicitacoes": r[4], "confirmadas": r[5] or 0, "em_lista_de_espera": r[6] or 0}
        for r in rows]}


@relatorios.get("/taxa-reprovacao")
def taxa_reprovacao(semestre: Optional[Semestre] = None, db: Session = Depends(get_db)):
    """Taxa = reprovados / (aprovados + reprovados). Trancamentos sao informados
    mas nao entram no calculo."""
    stmt = (select(Disciplina.id, Disciplina.codigo, Disciplina.nome,
                   func.sum(case((Historico.situacao == SH.aprovado, 1), else_=0)),
                   func.sum(case((Historico.situacao == SH.reprovado, 1), else_=0)),
                   func.sum(case((Historico.situacao == SH.trancado, 1), else_=0)))
            .join(Historico, Historico.disciplina_id == Disciplina.id)
            .group_by(Disciplina.id).order_by(Disciplina.codigo))
    if semestre:
        stmt = stmt.where(Historico.semestre == semestre)
    out = []
    for did, cod, nome, apr, rep, tranc in db.execute(stmt).all():
        apr, rep, tranc = apr or 0, rep or 0, tranc or 0
        avaliados = apr + rep
        out.append({"disciplina_id": did, "codigo": cod, "nome": nome,
                    "aprovados": apr, "reprovados": rep, "trancados": tranc,
                    "taxa_reprovacao": round(rep / avaliados, 4) if avaliados else None})
    out.sort(key=lambda d: (-(d["taxa_reprovacao"] or 0), d["codigo"]))
    return {"semestre": semestre, "disciplinas": out}


@relatorios.get("/ocupacao-turmas")
def ocupacao(semestre: Semestre, db: Session = Depends(get_db)):
    """Ocupacao = matriculas confirmadas / vagas, por turma e agregada por
    departamento (turmas canceladas sao listadas, mas fora do agregado)."""
    turmas = db.scalars(select(Turma).join(Disciplina).where(Turma.semestre == semestre)
                        .order_by(Disciplina.departamento, Turma.id)).all()
    deps: dict[str, dict] = {}
    for t in turmas:
        conf = sum(1 for m in t.matriculas if m.estado == EM.confirmada)
        espera = sum(1 for m in t.matriculas if m.estado == EM.lista_de_espera)
        d = deps.setdefault(t.disciplina.departamento, {
            "departamento": t.disciplina.departamento, "vagas": 0, "confirmadas": 0,
            "turmas": []})
        d["turmas"].append({"turma_id": t.id, "disciplina": t.disciplina.codigo,
                            "estado": t.estado.value, "vagas": t.vagas,
                            "confirmadas": conf, "lista_de_espera": espera,
                            "ocupacao": round(conf / t.vagas, 4)})
        if t.estado != ET.cancelada:
            d["vagas"] += t.vagas
            d["confirmadas"] += conf
    for d in deps.values():
        d["ocupacao"] = round(d["confirmadas"] / d["vagas"], 4) if d["vagas"] else None
    return {"semestre": semestre, "departamentos": list(deps.values())}
