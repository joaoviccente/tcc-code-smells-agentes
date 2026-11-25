from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.tarifa import TarifaResponse, CobrarMensalidadeResponse
from app.services.tarifa_service import TarifaService

router = APIRouter(tags=["Tarifas"])


@router.get("/contas/{conta_id}/tarifas", response_model=List[TarifaResponse])
def listar_tarifas_por_conta(conta_id: int, db: Session = Depends(get_db)):
    """Lista todas as tarifas (cobradas ou isentas) vinculadas a uma conta."""
    return TarifaService.listar_por_conta(db, conta_id)


@router.post("/tarifas/cobrar-mensalidades", response_model=CobrarMensalidadeResponse)
def cobrar_tarifas_mensais(
    conta_id: Optional[int] = Query(None, description="Opcional: ID de uma conta específica para cobrar"),
    db: Session = Depends(get_db),
):
    """
    Processa a cobrança de tarifa mensal das contas ativas:
    - Comum: R$ 30,00
    - Premium: sem tarifa mensal (R$ 0,00)
    - Empresarial: R$ 120,00
    """
    return TarifaService.cobrar_mensalidades(db, conta_id=conta_id)
