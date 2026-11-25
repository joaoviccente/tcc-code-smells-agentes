from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import clock
from app.database import get_db
from app.errors import RegraViolada
from app.schemas import (
    PADRAO_MES, ContaNegativa, MovimentacaoCliente, ReceitaTarifas, ResultadoRotina,
)
from app.services import relatorios as service
from app.services import rotinas

router = APIRouter(prefix="/relatorios", tags=["Relatorios"])
router_rotinas = APIRouter(prefix="/rotinas", tags=["Rotinas"])


def _validar_periodo(inicio: date | None, fim: date | None):
    if inicio and fim and inicio > fim:
        raise RegraViolada("Data inicial posterior a data final")


@router.get("/clientes-maior-movimentacao", response_model=list[MovimentacaoCliente])
def clientes_maior_movimentacao(
    inicio: date | None = None,
    fim: date | None = None,
    limite: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _validar_periodo(inicio, fim)
    return service.clientes_maior_movimentacao(db, inicio, fim, limite)


@router.get("/contas-saldo-negativo", response_model=list[ContaNegativa])
def contas_saldo_negativo(db: Session = Depends(get_db)):
    return service.contas_saldo_negativo(db, clock.agora())


@router.get("/receita-tarifas", response_model=ReceitaTarifas)
def receita_tarifas(
    inicio: date | None = None,
    fim: date | None = None,
    db: Session = Depends(get_db),
):
    _validar_periodo(inicio, fim)
    return service.receita_tarifas(db, inicio, fim)


@router_rotinas.post("/processamento-diario", response_model=ResultadoRotina)
def processamento_diario(
    data_referencia: datetime | None = None, db: Session = Depends(get_db)
):
    """Fecha faturas, marca atrasos, calcula juros, bloqueia cartoes com mais de 10 dias
    de atraso e bloqueia clientes com saldo negativo ha mais de 30 dias. Executado
    tambem automaticamente pelo agendador interno."""
    agora = data_referencia or clock.agora()
    return ResultadoRotina(data_referencia=agora, detalhes=rotinas.processamento_diario(db, agora))


@router_rotinas.post("/tarifas-mensais", response_model=ResultadoRotina)
def tarifas_mensais(
    competencia: str | None = Query(None, pattern=PADRAO_MES), db: Session = Depends(get_db)
):
    """Gera (idempotente) a tarifa mensal de cada conta para a competencia e re-tenta
    a cobranca de tarifas pendentes."""
    agora = clock.agora()
    return ResultadoRotina(data_referencia=agora,
                           detalhes=rotinas.tarifas_mensais(db, competencia, agora))
