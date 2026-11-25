from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.fatura_service import FaturaService
from app.services.relatorio_service import RelatorioService

router = APIRouter(prefix="/rotinas", tags=["Rotinas de Negócio"])


@router.post("/processar-faturas-atrasadas")
def processar_faturas_atrasadas(db: Session = Depends(get_db)):
    """
    Varre faturas com vencimento expirado, aplica juros de acordo com a categoria
    do cliente e bloqueia cartões com mais de 10 dias de atraso (Regra 5).
    """
    total = FaturaService.processar_todas_faturas_atrasadas(db)
    return {"status": "sucesso", "faturas_processadas": total}


@router.post("/processar-saldo-negativo")
def processar_saldo_negativo(db: Session = Depends(get_db)):
    """
    Varre contas com saldo negativo por mais de 30 dias, bloqueando o cliente
    titular e todos os seus cartões vinculados (Regra 6).
    """
    afetados = RelatorioService.processar_saldo_negativo_30_dias(db)
    return {"status": "sucesso", "clientes_bloqueados": afetados}
