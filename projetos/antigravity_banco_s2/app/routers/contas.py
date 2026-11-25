from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import EstadoConta, TipoConta, EstadoTarifa
from app.schemas.conta import ContaCreate, ContaUpdate, ContaResponse, ContaEncerrarResponse
from app.schemas.transacao import ExtratoResponse
from app.schemas.tarifa import TarifaResponse
from app.services import conta_service, transacao_service, tarifa_service

router = APIRouter(prefix="/contas", tags=["Contas"])


@router.post("", response_model=ContaResponse, status_code=status.HTTP_201_CREATED)
def criar_conta(conta_in: ContaCreate, db: Session = Depends(get_db)):
    return conta_service.criar_conta(db, conta_in)


@router.get("", response_model=List[ContaResponse], status_code=status.HTTP_200_OK)
def listar_contas(
    cliente_id: Optional[int] = None,
    estado: Optional[EstadoConta] = None,
    tipo: Optional[TipoConta] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return conta_service.listar_contas(db, cliente_id, estado, tipo, skip, limit)


@router.get("/{conta_id}", response_model=ContaResponse, status_code=status.HTTP_200_OK)
def obter_conta(conta_id: int, db: Session = Depends(get_db)):
    return conta_service.obter_conta_por_id(db, conta_id)


@router.put("/{conta_id}", response_model=ContaResponse, status_code=status.HTTP_200_OK)
def atualizar_conta(
    conta_id: int,
    conta_in: ContaUpdate,
    db: Session = Depends(get_db),
):
    return conta_service.atualizar_conta(db, conta_id, conta_in)


@router.post("/{conta_id}/encerrar", response_model=ContaEncerrarResponse, status_code=status.HTTP_200_OK)
def encerrar_conta(conta_id: int, db: Session = Depends(get_db)):
    conta = conta_service.encerrar_conta(db, conta_id)
    return ContaEncerrarResponse(
        id=conta.id,
        numero=conta.numero,
        estado=conta.estado,
        mensagem="Conta encerrada com sucesso. Todos os cartões vinculados foram cancelados.",
    )


@router.delete("/{conta_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_conta(conta_id: int, db: Session = Depends(get_db)):
    conta_service.deletar_conta(db, conta_id)
    return None


@router.get("/{conta_id}/extrato", response_model=ExtratoResponse, status_code=status.HTTP_200_OK)
def obter_extrato(
    conta_id: int,
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    return transacao_service.obter_extrato(db, conta_id, data_inicio, data_fim)


@router.get("/{conta_id}/tarifas", response_model=List[TarifaResponse], status_code=status.HTTP_200_OK)
def listar_tarifas_da_conta(
    conta_id: int,
    estado: Optional[EstadoTarifa] = None,
    db: Session = Depends(get_db),
):
    return tarifa_service.listar_tarifas_por_conta(db, conta_id, estado)
