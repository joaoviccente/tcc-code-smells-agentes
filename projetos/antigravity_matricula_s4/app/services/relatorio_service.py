from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.disciplina import Disciplina
from app.models.turma import Turma
from app.models.matricula import Matricula
from app.models.historico import Historico
from app.config import EstadoMatricula, SituacaoHistorico


def relatorio_disciplinas_mais_procuradas(db: Session, semestre: Optional[str] = None) -> List[dict]:
    """
    Relatório: disciplinas mais procuradas no semestre.
    Considera todas as solicitações de matrícula realizadas para turmas da disciplina no semestre.
    """
    query = (
        db.query(
            Disciplina.id.label("disciplina_id"),
            Disciplina.codigo.label("codigo"),
            Disciplina.nome.label("nome"),
            Disciplina.departamento.label("departamento"),
            func.count(Matricula.id).label("total_solicitacoes")
        )
        .join(Turma, Turma.disciplina_id == Disciplina.id)
        .join(Matricula, Matricula.turma_id == Turma.id)
    )

    if semestre:
        query = query.filter(Turma.semestre == semestre)

    results = (
        query.group_by(Disciplina.id, Disciplina.codigo, Disciplina.nome, Disciplina.departamento)
        .order_by(func.count(Matricula.id).desc())
        .all()
    )

    return [
        {
            "disciplina_id": r.disciplina_id,
            "codigo": r.codigo,
            "nome": r.nome,
            "departamento": r.departamento,
            "total_solicitacoes": r.total_solicitacoes,
        }
        for r in results
    ]


def relatorio_taxa_reprovacao(db: Session) -> List[dict]:
    """
    Relatório: taxa de reprovação por disciplina no histórico acadêmico.
    Taxa = (reprovado + reprovado_por_falta) / (aprovado + reprovado + reprovado_por_falta) * 100.
    """
    disciplinas = db.query(Disciplina).all()
    relatorio = []

    for d in disciplinas:
        historicos = db.query(Historico).filter(Historico.disciplina_id == d.id).all()
        aprovados = sum(1 for h in historicos if h.situacao == SituacaoHistorico.APROVADO)
        reprovados = sum(
            1 for h in historicos
            if h.situacao in [SituacaoHistorico.REPROVADO, SituacaoHistorico.REPROVADO_POR_FALTA]
        )
        total_avaliados = aprovados + reprovados

        taxa = (reprovados / total_avaliados * 100.0) if total_avaliados > 0 else 0.0

        relatorio.append({
            "disciplina_id": d.id,
            "codigo": d.codigo,
            "nome": d.nome,
            "departamento": d.departamento,
            "total_concluidos": total_avaliados,
            "total_aprovados": aprovados,
            "total_reprovados": reprovados,
            "taxa_reprovacao_percentual": round(taxa, 2),
        })

    # Ordenar por taxa decrescente
    relatorio.sort(key=lambda x: x["taxa_reprovacao_percentual"], reverse=True)
    return relatorio


def relatorio_ocupacao_departamentos(db: Session, semestre: Optional[str] = None) -> List[dict]:
    """
    Relatório: ocupação das turmas por departamento.
    Agrupa por departamento, calculando total de vagas oferecidas, confirmadas e taxa percentual de ocupação.
    """
    turmas_query = db.query(Turma).join(Disciplina)
    if semestre:
        turmas_query = turmas_query.filter(Turma.semestre == semestre)

    turmas = turmas_query.all()

    # Agrupar por departamento
    depto_dict: Dict[str, dict] = {}

    for t in turmas:
        depto = t.disciplina.departamento
        if depto not in depto_dict:
            depto_dict[depto] = {
                "departamento": depto,
                "total_turmas": 0,
                "total_vagas": 0,
                "vagas_ocupadas": 0,
                "turmas": []
            }

        vagas_confirmadas = db.query(Matricula).filter(
            Matricula.turma_id == t.id,
            Matricula.estado == EstadoMatricula.CONFIRMADA
        ).count()

        taxa_turma = (vagas_confirmadas / t.numero_vagas * 100.0) if t.numero_vagas > 0 else 0.0

        depto_dict[depto]["total_turmas"] += 1
        depto_dict[depto]["total_vagas"] += t.numero_vagas
        depto_dict[depto]["vagas_ocupadas"] += vagas_confirmadas
        depto_dict[depto]["turmas"].append({
            "turma_id": t.id,
            "disciplina_codigo": t.disciplina.codigo,
            "disciplina_nome": t.disciplina.nome,
            "semestre": t.semestre,
            "vagas_totais": t.numero_vagas,
            "vagas_ocupadas": vagas_confirmadas,
            "taxa_ocupacao_percentual": round(taxa_turma, 2),
        })

    resultado = []
    for depto_info in depto_dict.values():
        total_v = depto_info["total_vagas"]
        v_ocupadas = depto_info["vagas_ocupadas"]
        taxa_geral = (v_ocupadas / total_v * 100.0) if total_v > 0 else 0.0
        depto_info["taxa_ocupacao_percentual"] = round(taxa_geral, 2)
        resultado.append(depto_info)

    # Ordenar por taxa de ocupação decrescente
    resultado.sort(key=lambda x: x["taxa_ocupacao_percentual"], reverse=True)
    return resultado
