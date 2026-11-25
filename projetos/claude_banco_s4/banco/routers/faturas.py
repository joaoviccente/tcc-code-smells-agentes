from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import clock
from ..database import get_db
from ..schemas import FaturaOut, PagamentoFatura
from ..services import faturas
from ..services.comum import obter_fatura

router = APIRouter(prefix="/faturas", tags=["Faturas"])


@router.get("/{fatura_id}", response_model=FaturaOut)
def obter(fatura_id: int, db: Session = Depends(get_db)):
    fatura = obter_fatura(db, fatura_id)
    faturas.atualizar_situacao_fatura(fatura, clock.agora().date())
    db.commit()
    return fatura


@router.post("/{fatura_id}/pagamento", response_model=FaturaOut)
def pagar(fatura_id: int, dados: PagamentoFatura, db: Session = Depends(get_db)):
    """Registra o pagamento integral da fatura (valor + juros de atraso, se houver)."""
    return faturas.pagar_fatura(db, fatura_id, dados.valor)
