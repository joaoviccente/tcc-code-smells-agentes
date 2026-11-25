"""Conversao de entidades em respostas que incluem campos calculados."""
from sqlalchemy.orm import Session

from .models import Emprestimo, Reserva
from .schemas import EmprestimoSaida, MultaSaida, ReservaSaida
from .servicos import dias_atraso, posicao_na_fila


def emprestimo_saida(emp: Emprestimo) -> EmprestimoSaida:
    return EmprestimoSaida(
        id=emp.id,
        exemplar_id=emp.exemplar_id,
        usuario_id=emp.usuario_id,
        data_retirada=emp.data_retirada,
        data_prevista=emp.data_prevista,
        data_devolucao=emp.data_devolucao,
        estado=emp.estado,
        numero_renovacoes=emp.numero_renovacoes,
        dias_atraso=dias_atraso(emp),
        multa=MultaSaida.model_validate(emp.multa) if emp.multa else None,
    )


def reserva_saida(db: Session, r: Reserva) -> ReservaSaida:
    return ReservaSaida(
        id=r.id,
        livro_id=r.livro_id,
        usuario_id=r.usuario_id,
        data=r.data,
        estado=r.estado,
        posicao_fila=posicao_na_fila(db, r),
        exemplar_id=r.exemplar_id,
        expira_em=r.expira_em,
    )
