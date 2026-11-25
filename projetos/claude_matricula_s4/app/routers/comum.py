from sqlalchemy.orm import Session

from app import servicos as sv
from app.models import Historico, Matricula, Turma
from app.schemas import HistoricoSaida, MatriculaSaida, TurmaSaida


def matricula_saida(db: Session, m: Matricula) -> MatriculaSaida:
    s = MatriculaSaida.model_validate(m)
    s.posicao_lista_espera = sv.posicao_na_fila(db, m)
    return s


def turma_saida(db: Session, t: Turma) -> TurmaSaida:
    s = TurmaSaida.model_validate(t)
    s.vagas_ocupadas = sv.vagas_ocupadas(db, t)
    return s


def historico_saida(h: Historico) -> HistoricoSaida:
    return HistoricoSaida(
        id=h.id, aluno_id=h.aluno_id, disciplina_id=h.disciplina_id,
        codigo_disciplina=h.disciplina.codigo, nome_disciplina=h.disciplina.nome,
        semestre=h.semestre, nota=h.nota, situacao=h.situacao,
        observacao=h.observacao, matricula_id=h.matricula_id)
