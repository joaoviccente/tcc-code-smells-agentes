"""Serviço de geração de relatórios gerenciais acadêmicos."""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.disciplina import Disciplina
from app.models.turma import Turma
from app.models.matricula import Matricula
from app.models.historico import Historico
from app.models.enums import EstadoMatricula, SituacaoHistorico
from app.schemas.relatorios import (
    DisciplinaMaisProcuradaResponse,
    TaxaReprovacaoResponse,
    OcupacaoTurmaItem,
    OcupacaoDepartamentoResponse,
)


def relatorio_disciplinas_mais_procuradas(
    db: Session,
    semestre: Optional[str] = None
) -> List[DisciplinaMaisProcuradaResponse]:
    """
    Retorna as disciplinas mais procuradas no semestre especificado,
    ordenadas pelo total de solicitações de matrícula em ordem decrescente.
    """
    query = db.query(Disciplina)
    disciplinas = query.all()

    resultados = []
    for d in disciplinas:
        turmas_query = db.query(Turma.id).filter(Turma.disciplina_id == d.id)
        if semestre:
            turmas_query = turmas_query.filter(Turma.semestre == semestre)

        turma_ids = [t[0] for t in turmas_query.all()]
        if not turma_ids:
            if semestre:
                continue
            total_solicitacoes = 0
            total_confirmadas = 0
            total_espera = 0
        else:
            total_solicitacoes = db.query(Matricula).filter(
                Matricula.turma_id.in_(turma_ids)
            ).count()

            total_confirmadas = db.query(Matricula).filter(
                Matricula.turma_id.in_(turma_ids),
                Matricula.estado == EstadoMatricula.CONFIRMADA
            ).count()

            total_espera = db.query(Matricula).filter(
                Matricula.turma_id.in_(turma_ids),
                Matricula.estado == EstadoMatricula.LISTA_DE_ESPERA
            ).count()

        resultados.append(
            DisciplinaMaisProcuradaResponse(
                disciplina_id=d.id,
                codigo=d.codigo,
                nome=d.nome,
                departamento=d.departamento,
                total_solicitacoes=total_solicitacoes,
                total_confirmadas=total_confirmadas,
                total_espera=total_espera,
            )
        )

    resultados.sort(key=lambda x: (x.total_solicitacoes, x.total_confirmadas), reverse=True)
    return resultados


def relatorio_taxa_reprovacao(
    db: Session,
    semestre: Optional[str] = None
) -> List[TaxaReprovacaoResponse]:
    """
    Retorna a taxa de reprovação por disciplina no histórico.
    Taxa = (reprovações / total_avaliados) * 100.
    """
    disciplinas = db.query(Disciplina).order_by(Disciplina.codigo).all()
    resultados = []

    for d in disciplinas:
        q = db.query(Historico).filter(Historico.disciplina_id == d.id)
        if semestre:
            q = q.filter(Historico.semestre == semestre)

        registros = q.all()

        aprovados = sum(1 for r in registros if r.situacao == SituacaoHistorico.APROVADO)
        reprovados = sum(1 for r in registros if r.situacao in (
            SituacaoHistorico.REPROVADO,
            SituacaoHistorico.REPROVADO_POR_FALTA,
        ))
        trancados = sum(1 for r in registros if r.situacao == SituacaoHistorico.TRANCADO)

        total_avaliados = aprovados + reprovados
        taxa = round((reprovados / total_avaliados * 100.0), 2) if total_avaliados > 0 else 0.0

        resultados.append(
            TaxaReprovacaoResponse(
                disciplina_id=d.id,
                codigo=d.codigo,
                nome=d.nome,
                departamento=d.departamento,
                total_aprovados=aprovados,
                total_reprovados=reprovados,
                total_trancados=trancados,
                total_avaliados=total_avaliados,
                taxa_reprovacao_percentual=taxa,
            )
        )

    resultados.sort(key=lambda x: (x.taxa_reprovacao_percentual, x.total_reprovados), reverse=True)
    return resultados


def relatorio_ocupacao_departamentos(
    db: Session,
    semestre: Optional[str] = None
) -> List[OcupacaoDepartamentoResponse]:
    """
    Retorna a ocupação das turmas agrupadas por departamento.
    """
    turmas_query = db.query(Turma).join(Disciplina)
    if semestre:
        turmas_query = turmas_query.filter(Turma.semestre == semestre)

    turmas = turmas_query.all()

    # Agrupar turmas por departamento
    depto_turmas = {}
    for t in turmas:
        depto = t.disciplina.departamento
        if depto not in depto_turmas:
            depto_turmas[depto] = []
        depto_turmas[depto].append(t)

    # Considerar todos os departamentos cadastrados
    todos_deptos = db.query(Disciplina.departamento).distinct().all()
    for (dep,) in todos_deptos:
        if dep not in depto_turmas:
            depto_turmas[dep] = []

    resultados = []
    for depto, t_list in sorted(depto_turmas.items()):
        total_vagas_depto = 0
        total_ocupadas_depto = 0
        turmas_items = []

        for t in t_list:
            ocupadas = db.query(Matricula).filter(
                Matricula.turma_id == t.id,
                Matricula.estado == EstadoMatricula.CONFIRMADA
            ).count()

            total_vagas_depto += t.numero_vagas
            total_ocupadas_depto += ocupadas

            taxa_turma = round((ocupadas / t.numero_vagas * 100.0), 2) if t.numero_vagas > 0 else 0.0

            turmas_items.append(
                OcupacaoTurmaItem(
                    turma_id=t.id,
                    disciplina_codigo=t.disciplina.codigo,
                    disciplina_nome=t.disciplina.nome,
                    semestre=t.semestre,
                    professor=t.professor,
                    horario=t.horario,
                    estado=t.estado.value,
                    vagas_totais=t.numero_vagas,
                    vagas_ocupadas=ocupadas,
                    taxa_ocupacao_percentual=taxa_turma,
                )
            )

        taxa_geral = round((total_ocupadas_depto / total_vagas_depto * 100.0), 2) if total_vagas_depto > 0 else 0.0

        resultados.append(
            OcupacaoDepartamentoResponse(
                departamento=depto,
                vagas_totais=total_vagas_depto,
                vagas_ocupadas=total_ocupadas_depto,
                taxa_ocupacao_geral_percentual=taxa_geral,
                turmas=turmas_items,
            )
        )

    return resultados
