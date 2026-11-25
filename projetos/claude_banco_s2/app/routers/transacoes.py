from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import clock
from app.database import get_db
from app.models import Transacao
from app.schemas import DepositoEntrada, SaqueEntrada, TransacaoSaida, TransferenciaEntrada
from app.services import transacoes as service
from app.services.comum import obter

router = APIRouter(prefix="/transacoes", tags=["Transacoes"])


@router.post("/depositos", response_model=TransacaoSaida, status_code=status.HTTP_201_CREATED)
def depositar(dados: DepositoEntrada, db: Session = Depends(get_db)):
    return service.depositar(db, dados.conta_id, dados.valor, dados.descricao, clock.agora())


@router.post("/saques", response_model=TransacaoSaida, status_code=status.HTTP_201_CREATED)
def sacar(dados: SaqueEntrada, db: Session = Depends(get_db)):
    return service.sacar(db, dados.conta_id, dados.valor, dados.descricao, clock.agora())


@router.post("/transferencias", response_model=TransacaoSaida,
             status_code=status.HTTP_201_CREATED)
def transferir(dados: TransferenciaEntrada, db: Session = Depends(get_db)):
    return service.transferir(
        db, dados.conta_origem_id, dados.conta_destino_id, dados.valor, dados.descricao,
        clock.agora(),
    )


@router.post("/{transacao_id}/estorno", response_model=TransacaoSaida,
             status_code=status.HTTP_201_CREATED)
def estornar(transacao_id: int, db: Session = Depends(get_db)):
    return service.estornar(db, transacao_id, clock.agora())


@router.get("/{transacao_id}", response_model=TransacaoSaida)
def obter_transacao(transacao_id: int, db: Session = Depends(get_db)):
    return obter(db, Transacao, transacao_id, "Transacao")
