from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.conta import Conta
from app.models.cliente import Cliente
from app.models.cartao import Cartao
from app.models.fatura import Fatura
from app.schemas.conta import ContaCreate, ContaUpdate
from app.config import EstadoConta, EstadoCartao, EstadoFatura, TipoConta, get_current_time


def criar_conta(db: Session, conta_in: ContaCreate) -> Conta:
    cliente = db.query(Cliente).filter(Cliente.id == conta_in.cliente_id).first()
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cliente com ID {conta_in.cliente_id} não encontrado."
        )

    # Verifica unicidade do número da conta
    if db.query(Conta).filter(Conta.numero == conta_in.numero).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe uma conta com o número {conta_in.numero}."
        )

    # Se saldo inicial for negativo, deve respeitar limite de crédito
    if conta_in.saldo < Decimal("0.00"):
        if conta_in.saldo < -conta_in.limite_credito:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Saldo inicial não pode ser menor que o limite de crédito negativo."
            )
        data_negativo = get_current_time()
    else:
        data_negativo = None

    db_conta = Conta(
        cliente_id=conta_in.cliente_id,
        numero=conta_in.numero,
        tipo=conta_in.tipo,
        saldo=conta_in.saldo,
        limite_credito=conta_in.limite_credito,
        estado=conta_in.estado,
        data_saldo_negativo_desde=data_negativo,
    )
    db.add(db_conta)
    db.commit()
    db.refresh(db_conta)
    return db_conta


def listar_contas(
    db: Session,
    cliente_id: Optional[int] = None,
    estado: Optional[EstadoConta] = None,
    tipo: Optional[TipoConta] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Conta]:
    query = db.query(Conta)
    if cliente_id:
        query = query.filter(Conta.cliente_id == cliente_id)
    if estado:
        query = query.filter(Conta.estado == estado)
    if tipo:
        query = query.filter(Conta.tipo == tipo)
    return query.offset(skip).limit(limit).all()


def obter_conta_por_id(db: Session, conta_id: int) -> Conta:
    conta = db.query(Conta).filter(Conta.id == conta_id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta com ID {conta_id} não encontrada."
        )
    return conta


def atualizar_conta(db: Session, conta_id: int, conta_in: ContaUpdate) -> Conta:
    conta = obter_conta_por_id(db, conta_id)

    if conta_in.tipo is not None:
        conta.tipo = conta_in.tipo
    if conta_in.limite_credito is not None:
        if conta.saldo < -conta_in.limite_credito:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Novo limite de crédito R$ {conta_in.limite_credito} é insuficiente para cobrir o saldo devedor atual de R$ {abs(conta.saldo)}."
            )
        conta.limite_credito = conta_in.limite_credito
    if conta_in.estado is not None:
        conta.estado = conta_in.estado

    db.commit()
    db.refresh(conta)
    return conta


def encerrar_conta(db: Session, conta_id: int) -> Conta:
    """
    Regra 7: O encerramento de conta exige saldo zero e nenhuma fatura aberta.
    Ao encerrar, todos os cartoes da conta sao cancelados.
    """
    conta = obter_conta_por_id(db, conta_id)

    if conta.estado == EstadoConta.ENCERRADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A conta já se encontra encerrada."
        )

    # 1. Exige saldo exatamente zero
    if conta.saldo != Decimal("0.00"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Para encerrar a conta, o saldo deve ser exatamente R$ 0,00. Saldo atual: R$ {conta.saldo}."
        )

    # 2. Exige nenhuma fatura aberta ou atrasada
    faturas_pendentes = (
        db.query(Fatura)
        .join(Cartao, Fatura.cartao_id == Cartao.id)
        .filter(
            Cartao.conta_id == conta.id,
            Fatura.estado.in_([EstadoFatura.ABERTA, EstadoFatura.ATRASADA])
        )
        .all()
    )
    if faturas_pendentes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Não é possível encerrar a conta: existem {len(faturas_pendentes)} fatura(s) aberta(s) ou atrasada(s) nos cartões vinculados."
        )

    # 3. Cancela todos os cartões vinculados à conta
    for cartao in conta.cartoes:
        cartao.estado = EstadoCartao.CANCELADO

    # 4. Altera o estado da conta para encerrada
    conta.estado = EstadoConta.ENCERRADA
    conta.data_saldo_negativo_desde = None

    db.commit()
    db.refresh(conta)
    return conta


def deletar_conta(db: Session, conta_id: int) -> None:
    conta = obter_conta_por_id(db, conta_id)
    if conta.saldo != Decimal("0.00"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Não é possível deletar conta com saldo diferente de zero (Saldo: R$ {conta.saldo})."
        )
    if conta.estado != EstadoConta.ENCERRADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas contas encerradas podem ser removidas do sistema."
        )
    db.delete(conta)
    db.commit()
