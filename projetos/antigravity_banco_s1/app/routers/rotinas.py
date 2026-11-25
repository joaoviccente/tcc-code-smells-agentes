from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.rotina_service import RotinaService

router = APIRouter(prefix="/rotinas", tags=["Rotinas de Manutenção"])


@router.post("/verificar-inadimplencia", status_code=status.HTTP_200_OK)
def verificar_inadimplencia(
    data_referencia: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    """
    Executa a rotina de verificação de inadimplência:
    - Regra 5: faturas atrasadas atualizam juros conforme categoria; cartões com fatura atrasada há mais de 10 dias são bloqueados.
    - Regra 6: contas com saldo negativo há mais de 30 dias bloqueiam o cliente titular e todos os seus cartões.
    """
    return RotinaService.processar_inadimplencia(db, data_referencia=data_referencia)
