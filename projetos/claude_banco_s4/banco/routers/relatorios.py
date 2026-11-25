from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import clock
from ..database import get_db
from ..errors import RegraViolada
from ..schemas import ContaNegativa, MovimentacaoCliente, ReceitaCategoria, ResultadoRotina
from ..services import relatorios, rotinas

router = APIRouter()


def _validar_periodo(inicio, fim):
    if inicio and fim and inicio > fim:
        raise RegraViolada("'inicio' deve ser anterior a 'fim'")


@router.get("/relatorios/clientes-maior-movimentacao", response_model=list[MovimentacaoCliente],
            tags=["Relatorios"])
def maior_movimentacao(
    inicio: datetime,
    fim: datetime,
    limite: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _validar_periodo(inicio, fim)
    return relatorios.maior_movimentacao(db, inicio, fim, limite)


@router.get("/relatorios/contas-saldo-negativo", response_model=list[ContaNegativa], tags=["Relatorios"])
def contas_negativas(db: Session = Depends(get_db)):
    return relatorios.contas_negativas(db)


@router.get("/relatorios/receita-tarifas", response_model=list[ReceitaCategoria], tags=["Relatorios"])
def receita_tarifas(inicio: datetime | None = None, fim: datetime | None = None, db: Session = Depends(get_db)):
    _validar_periodo(inicio, fim)
    return relatorios.receita_tarifas(db, inicio, fim)


@router.post("/rotinas/processamento-diario", response_model=ResultadoRotina, tags=["Rotinas"])
def processamento_diario(data_referencia: date | None = None, db: Session = Depends(get_db)):
    """Fecha faturas, aplica atraso/juros, bloqueia cartoes e clientes e cobra tarifas mensais.
    Executada automaticamente a cada hora; pode tambem ser disparada manualmente."""
    return rotinas.processar(db, data_referencia or clock.agora().date())
