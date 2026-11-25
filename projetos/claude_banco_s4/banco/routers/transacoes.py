from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import Deposito, OperacaoOut, Saque, TransacaoOut, Transferencia
from ..services import transacoes
from ..services.comum import obter_transacao

router = APIRouter(prefix="/transacoes", tags=["Transacoes"])


def _saida(r: transacoes.ResultadoOperacao) -> dict:
    return {"transacao": r.transacao, "tarifa": r.tarifa, "saldos": r.saldos}


@router.post("/deposito", response_model=OperacaoOut, status_code=status.HTTP_201_CREATED)
def deposito(dados: Deposito, db: Session = Depends(get_db)):
    return _saida(transacoes.depositar(db, dados.conta_id, dados.valor, dados.descricao))


@router.post("/saque", response_model=OperacaoOut, status_code=status.HTTP_201_CREATED)
def saque(dados: Saque, db: Session = Depends(get_db)):
    return _saida(transacoes.sacar(db, dados.conta_id, dados.valor, dados.descricao))


@router.post("/transferencia", response_model=OperacaoOut, status_code=status.HTTP_201_CREATED)
def transferencia(dados: Transferencia, db: Session = Depends(get_db)):
    return _saida(
        transacoes.transferir(db, dados.conta_origem_id, dados.conta_destino_id, dados.valor, dados.descricao)
    )


@router.post("/{transacao_id}/estorno", response_model=OperacaoOut, status_code=status.HTTP_201_CREATED)
def estorno(transacao_id: int, db: Session = Depends(get_db)):
    """Estorna transacao efetivada em ate 24h, revertendo os saldos e registrando transacao de estorno."""
    return _saida(transacoes.estornar(db, transacao_id))


@router.get("/{transacao_id}", response_model=TransacaoOut)
def obter(transacao_id: int, db: Session = Depends(get_db)):
    return obter_transacao(db, transacao_id)
