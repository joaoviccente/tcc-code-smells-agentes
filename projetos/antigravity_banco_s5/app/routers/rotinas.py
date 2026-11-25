from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import rotinas_service

router = APIRouter(prefix="/rotinas", tags=["Rotinas Automáticas / Sistema"])


class VerificacaoInadimplenciaRequest(BaseModel):
    data_referencia: Optional[datetime] = None


@router.post("/verificar-inadimplencia", status_code=status.HTTP_200_OK)
def verificar_inadimplencia(
    req: Optional[VerificacaoInadimplenciaRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Executa a rotina periódica de verificação de inadimplência:
    - Regra 5: Faturas vencidas são marcadas como 'atrasada' e acumulam juros da categoria.
      Se atraso > 10 dias, bloqueia o cartão associado.
    - Regra 6: Contas com saldo negativo há mais de 30 dias bloqueiam o cliente titular
      e todos os seus cartões.
    """
    data_ref = req.data_referencia if req else None
    return rotinas_service.executar_verificacao_inadimplencia(db, data_referencia=data_ref)
