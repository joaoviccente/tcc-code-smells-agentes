from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import servicos
from app.deps import get_db
from app.models import Multa
from app.schemas import MultaSaida

router = APIRouter(prefix="/multas", tags=["Multas"])


@router.get("/{multa_id}", response_model=MultaSaida)
def detalhar(multa_id: int, db: Session = Depends(get_db)):
    return servicos.obter(db, Multa, multa_id, "Multa")


@router.post("/{multa_id}/pagamento", response_model=MultaSaida)
def pagar(multa_id: int, db: Session = Depends(get_db)):
    return servicos.pagar_multa(db, servicos.obter(db, Multa, multa_id, "Multa"))
