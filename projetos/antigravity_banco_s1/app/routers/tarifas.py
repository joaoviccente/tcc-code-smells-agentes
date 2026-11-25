from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.tarifa import EstadoTarifa
from app.schemas.tarifa import TarifaResponse
from app.services.tarifa_service import TarifaService

router = APIRouter(tags=["Tarifas"])


@router.get(
    "/contas/{conta_id}/tarifas",
    response_model=List[TarifaResponse],
    status_code=status.HTTP_200_OK,
)
def listar_tarifas_por_conta(
    conta_id: int,
    estado: Optional[EstadoTarifa] = None,
    db: Session = Depends(get_db),
):
    """Lista as tarifas vinculadas a uma conta bancária."""
    return TarifaService.listar_tarifas_por_conta(
        db, conta_id, estado=estado.value if estado else None
    )


@router.post(
    "/contas/{conta_id}/tarifas/cobrar-mensalidade",
    response_model=TarifaResponse,
    status_code=status.HTTP_201_CREATED,
)
def cobrar_tarifa_mensal(conta_id: int, db: Session = Depends(get_db)):
    """
    Aplica a cobrança de tarifa mensal conforme categoria do cliente:
    - Comum: R$ 30,00
    - Premium: R$ 0,00 (isenta)
    - Empresarial: R$ 120,00
    """
    return TarifaService.cobrar_tarifa_mensal(db, conta_id)
