from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.disciplina import Disciplina
from app.models.turma import Turma
from app.models.matricula import Matricula
from app.models.historico import Historico
from app.models.enums import EstadoMatricula, SituacaoHistorico

def get_disciplinas_mais_procuradas(
    db: Session,
    semestre: Optional[str] = None
) -> Dict[str, Any]:
    """
    Relatório: Disciplinas mais procuradas no semestre.
    Ordenado pelo número total de solicitações de matrícula decrescente.
    """
    disciplinas = db.query(Disciplina).all()
    resultado = []

    for d in disciplinas:
        query_m = db.query(Matricula).join(Turma).filter(Turma.disciplina_id == d.id)
        if semestre:
            query_m = query_m.filter(Turma.semestre == semestre)

        matriculas = query_m.all()
        total_solicitacoes = len(matriculas)
        total_confirmadas = sum(1 for m in matriculas if m.estado == EstadoMatricula.CONFIRMADA)
        total_fila = sum(1 for m in matriculas if m.estado == EstadoMatricula.LISTA_DE_ESPERA)

        resultado.append({
            "disciplina_id": d.id,
            "codigo": d.codigo,
            "nome": d.nome,
            "departamento": d.departamento,
            "total_solicitacoes": total_solicitacoes,
            "total_confirmadas": total_confirmadas,
            "total_fila_espera": total_fila
        })

    # Ordenar pelas mais procuradas
    resultado.sort(key=lambda x: x["total_solicitacoes"], reverse=True)

    return {
        "semestre": semestre,
        "disciplinas": resultado
    }


def get_taxa_reprovacao_por_disciplina(db: Session) -> Dict[str, Any]:
    """
    Relatório: Taxa de reprovação por disciplina baseada no histórico.
    """
    disciplinas = db.query(Disciplina).all()
    resultado = []

    for d in disciplinas:
        historicos = db.query(Historico).filter(Historico.disciplina_id == d.id).all()
        total = len(historicos)
        aprovados = sum(1 for h in historicos if h.situacao == SituacaoHistorico.APROVADO)
        reprovados = sum(
            1 for h in historicos
            if h.situacao in (SituacaoHistorico.REPROVADO, SituacaoHistorico.REPROVADO_POR_FALTA)
        )
        trancados = sum(1 for h in historicos if h.situacao == SituacaoHistorico.TRANCADO)

        taxa = round((reprovados / total * 100), 2) if total > 0 else 0.0

        resultado.append({
            "disciplina_id": d.id,
            "codigo": d.codigo,
            "nome": d.nome,
            "departamento": d.departamento,
            "total_registros": total,
            "aprovados": aprovados,
            "reprovados": reprovados,
            "trancados": trancados,
            "taxa_reprovacao_percentual": taxa
        })

    # Ordenar por maior taxa de reprovação
    resultado.sort(key=lambda x: x["taxa_reprovacao_percentual"], reverse=True)

    return {"disciplinas": resultado}


def get_ocupacao_turmas_por_departamento(
    db: Session,
    semestre: Optional[str] = None
) -> Dict[str, Any]:
    """
    Relatório: Ocupação das turmas agrupadas por departamento.
    """
    query_turmas = db.query(Turma).join(Disciplina)
    if semestre:
        query_turmas = query_turmas.filter(Turma.semestre == semestre)

    turmas = query_turmas.all()

    dept_map: Dict[str, List[Turma]] = {}
    for t in turmas:
        dept = t.disciplina.departamento
        if dept not in dept_map:
            dept_map[dept] = []
        dept_map[dept].append(t)

    resultado = []
    for dept, lista_turmas in dept_map.items():
        total_vagas = sum(t.numero_vagas for t in lista_turmas)
        total_ocupadas = 0
        turmas_detalhes = []

        for t in lista_turmas:
            ocupadas = (
                db.query(Matricula)
                .filter(
                    Matricula.turma_id == t.id,
                    Matricula.estado == EstadoMatricula.CONFIRMADA
                )
                .count()
            )
            total_ocupadas += ocupadas
            taxa_turma = round((ocupadas / t.numero_vagas * 100), 2) if t.numero_vagas > 0 else 0.0

            turmas_detalhes.append({
                "turma_id": t.id,
                "disciplina_codigo": t.disciplina.codigo,
                "disciplina_nome": t.disciplina.nome,
                "professor": t.professor,
                "horario": t.horario,
                "numero_vagas": t.numero_vagas,
                "vagas_ocupadas": ocupadas,
                "taxa_ocupacao_percentual": taxa_turma,
                "estado": t.estado.value
            })

        taxa_geral = round((total_ocupadas / total_vagas * 100), 2) if total_vagas > 0 else 0.0

        resultado.append({
            "departamento": dept,
            "total_turmas": len(lista_turmas),
            "total_vagas_ofertadas": total_vagas,
            "total_vagas_ocupadas": total_ocupadas,
            "taxa_ocupacao_geral_percentual": taxa_geral,
            "turmas": turmas_detalhes
        })

    # Ordenar por nome do departamento
    resultado.sort(key=lambda x: x["departamento"])

    return {
        "semestre": semestre,
        "departamentos": resultado
    }
