from datetime import date, datetime
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.rotinas_service import RotinasService

router = APIRouter(prefix="/rotinas", tags=["Rotinas Automáticas"])


@router.post("/processar-faturas-atrasadas")
def processar_faturas_atrasadas(
    data_referencia: Optional[date] = Query(None, description="Data base de corte (padrão: hoje)"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Executa a rotina da Regra 5:
    - Identifica faturas vencidas não pagas e altera estado para ATRASADA;
    - Calcula juros conforme a categoria do cliente;
    - Bloqueia o cartão caso o atraso seja superior a 10 dias.
    """
    return RotinasService.processar_faturas_atrasadas(db, data_referencia=data_referencia)


@router.post("/processar-contas-negativas")
def processar_contas_negativas(
    data_referencia: Optional[datetime] = Query(None, description="Data/hora base de corte (padrão: agora)"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Executa a rotina da Regra 6:
    - Identifica contas com saldo negativo por mais de 30 dias;
    - Bloqueia o cliente e todos os seus cartões.
    """
    return RotinasService.processar_contas_negativas(db, data_referencia=data_referencia)
