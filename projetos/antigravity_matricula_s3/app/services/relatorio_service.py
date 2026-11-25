from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.disciplina import Disciplina
from app.models.turma import Turma
from app.models.matricula import Matricula
from app.models.historico import Historico
from app.models.enums import EstadoMatricula, SituacaoHistorico, EstadoTurma
from app.schemas.relatorio import (
    DisciplinaProcuraReport,
    TaxaReprovacaoReport,
    OcupacaoDepartamentoReport,
    OcupacaoTurmaItem
)

class RelatorioService:

    @staticmethod
    def disciplinas_mais_procuradas(db: Session, semestre: Optional[str] = None) -> List[DisciplinaProcuraReport]:
        """
        Relatório: disciplinas mais procuradas no semestre.
        Ordenado pelo total de solicitações (confirmadas + fila de espera + solicitadas).
        """
        disciplinas = db.query(Disciplina).all()
        resultado: List[DisciplinaProcuraReport] = []

        for d in disciplinas:
            query = db.query(Matricula).join(Turma).filter(Turma.disciplina_id == d.id)
            if semestre:
                query = query.filter(Turma.semestre == semestre)

            matriculas = query.all()
            total_solicitacoes = len(matriculas)
            total_confirmadas = sum(1 for m in matriculas if m.estado == EstadoMatricula.CONFIRMADA)
            total_espera = sum(1 for m in matriculas if m.estado == EstadoMatricula.LISTA_DE_ESPERA)

            resultado.append(
                DisciplinaProcuraReport(
                    disciplina_id=d.id,
                    codigo=d.codigo,
                    nome=d.nome,
                    departamento=d.departamento,
                    total_solicitacoes=total_solicitacoes,
                    total_confirmadas=total_confirmadas,
                    total_fila_espera=total_espera
                )
            )

        # Ordena da mais procurada para a menos procurada
        resultado.sort(key=lambda r: (r.total_solicitacoes, r.total_confirmadas), reverse=True)
        return resultado

    @staticmethod
    def taxa_reprovacao(db: Session, departamento: Optional[str] = None) -> List[TaxaReprovacaoReport]:
        """
        Relatório: taxa de reprovação por disciplina no histórico.
        """
        query_disc = db.query(Disciplina)
        if departamento:
            query_disc = query_disc.filter(Disciplina.departamento == departamento)
        disciplinas = query_disc.all()

        resultado: List[TaxaReprovacaoReport] = []

        for d in disciplinas:
            historicos = db.query(Historico).filter(Historico.disciplina_id == d.id).all()
            avaliados = [h for h in historicos if h.situacao in (
                SituacaoHistorico.APROVADO,
                SituacaoHistorico.REPROVADO,
                SituacaoHistorico.REPROVADO_POR_FALTA
            )]
            total_avaliados = len(avaliados)
            total_aprovados = sum(1 for h in avaliados if h.situacao == SituacaoHistorico.APROVADO)
            total_reprovados = sum(
                1 for h in avaliados if h.situacao in (SituacaoHistorico.REPROVADO, SituacaoHistorico.REPROVADO_POR_FALTA)
            )

            taxa = (total_reprovados / total_avaliados * 100.0) if total_avaliados > 0 else 0.0

            resultado.append(
                TaxaReprovacaoReport(
                    disciplina_id=d.id,
                    codigo=d.codigo,
                    nome=d.nome,
                    departamento=d.departamento,
                    total_avaliados=total_avaliados,
                    total_aprovados=total_aprovados,
                    total_reprovados=total_reprovados,
                    taxa_reprovacao_percentual=round(taxa, 2)
                )
            )

        # Ordena pela maior taxa de reprovação
        resultado.sort(key=lambda r: (r.taxa_reprovacao_percentual, r.total_avaliados), reverse=True)
        return resultado

    @staticmethod
    def ocupacao_departamentos(db: Session, semestre: Optional[str] = None) -> List[OcupacaoDepartamentoReport]:
        """
        Relatório: ocupação das turmas por departamento.
        """
        departamentos_rows = db.query(Disciplina.departamento).distinct().all()
        departamentos = [r[0] for r in departamentos_rows]

        resultado: List[OcupacaoDepartamentoReport] = []

        for dep in departamentos:
            query_turmas = db.query(Turma).join(Disciplina).filter(
                Disciplina.departamento == dep,
                Turma.estado != EstadoTurma.CANCELADA
            )
            if semestre:
                query_turmas = query_turmas.filter(Turma.semestre == semestre)

            turmas = query_turmas.all()
            total_turmas = len(turmas)
            total_vagas = sum(t.numero_vagas for t in turmas)

            turma_items: List[OcupacaoTurmaItem] = []
            total_confirmadas_dep = 0

            for t in turmas:
                conf_count = db.query(Matricula).filter(
                    Matricula.turma_id == t.id,
                    Matricula.estado == EstadoMatricula.CONFIRMADA
                ).count()
                total_confirmadas_dep += conf_count

                taxa_t = (conf_count / t.numero_vagas * 100.0) if t.numero_vagas > 0 else 0.0
                turma_items.append(
                    OcupacaoTurmaItem(
                        turma_id=t.id,
                        disciplina_codigo=t.disciplina.codigo,
                        disciplina_nome=t.disciplina.nome,
                        semestre=t.semestre,
                        professor=t.professor,
                        numero_vagas=t.numero_vagas,
                        confirmadas=conf_count,
                        taxa_ocupacao_percentual=round(taxa_t, 2)
                    )
                )

            taxa_dep = (total_confirmadas_dep / total_vagas * 100.0) if total_vagas > 0 else 0.0

            resultado.append(
                OcupacaoDepartamentoReport(
                    departamento=dep,
                    total_turmas=total_turmas,
                    total_vagas=total_vagas,
                    total_confirmadas=total_confirmadas_dep,
                    taxa_ocupacao_percentual=round(taxa_dep, 2),
                    turmas=turma_items
                )
            )

        resultado.sort(key=lambda r: r.taxa_ocupacao_percentual, reverse=True)
        return resultado
