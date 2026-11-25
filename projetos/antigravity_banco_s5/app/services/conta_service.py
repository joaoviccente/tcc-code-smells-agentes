from decimal import Decimal
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.conta import Conta
from app.models.cliente import Cliente
from app.models.cartao import Cartao
from app.models.fatura import Fatura
from app.schemas.conta import ContaCreate, ContaUpdate
from app.config import EstadoConta, EstadoCartao, EstadoFatura, TipoConta
from app.utils import utc_now


def ajustar_rastreamento_saldo_negativo(conta: Conta) -> None:
    """Atualiza a data em que o saldo se tornou negativo ou a limpa se o saldo for >= 0."""
    if conta.saldo < Decimal("0.00"):
        if conta.data_saldo_negativo_inicio is None:
            conta.data_saldo_negativo_inicio = utc_now()
    else:
        conta.data_saldo_negativo_inicio = None


def criar_conta(db: Session, conta_in: ContaCreate) -> Conta:
    # Verificar se cliente existe
    cliente = db.query(Cliente).filter(Cliente.id == conta_in.cliente_id).first()
    if not cliente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cliente #{conta_in.cliente_id} não encontrado.",
        )

    # Verificar unicidade do número da conta
    if db.query(Conta).filter(Conta.numero == conta_in.numero).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe uma conta com o número {conta_in.numero}.",
        )

    db_conta = Conta(
        cliente_id=conta_in.cliente_id,
        numero=conta_in.numero,
        tipo=conta_in.tipo,
        saldo=Decimal("0.00"),
        limite_credito=conta_in.limite_credito,
        estado=EstadoConta.ATIVA,
    )
    db.add(db_conta)
    db.commit()
    db.refresh(db_conta)
    return db_conta


def listar_contas(
    db: Session,
    cliente_id: Optional[int] = None,
    tipo: Optional[TipoConta] = None,
    estado: Optional[EstadoConta] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Conta]:
    query = db.query(Conta)
    if cliente_id:
        query = query.filter(Conta.cliente_id == cliente_id)
    if tipo:
        query = query.filter(Conta.tipo == tipo)
    if estado:
        query = query.filter(Conta.estado == estado)
    return query.offset(skip).limit(limit).all()


def obter_conta_por_id(db: Session, conta_id: int) -> Conta:
    conta = db.query(Conta).filter(Conta.id == conta_id).first()
    if not conta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conta #{conta_id} não encontrada.",
        )
    return conta


def atualizar_conta(db: Session, conta_id: int, conta_in: ContaUpdate) -> Conta:
    conta = obter_conta_por_id(db, conta_id)

    if conta.estado == EstadoConta.ENCERRADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível alterar dados de uma conta encerrada.",
        )

    if conta_in.tipo is not None:
        conta.tipo = conta_in.tipo
    if conta_in.limite_credito is not None:
        conta.limite_credito = conta_in.limite_credito
    if conta_in.estado is not None:
        if conta_in.estado == EstadoConta.ENCERRADA:
            return encerrar_conta(db, conta_id)
        conta.estado = conta_in.estado

    db.commit()
    db.refresh(conta)
    return conta


def encerrar_conta(db: Session, conta_id: int) -> Conta:
    """
    Regra de Negócio 7:
    O encerramento de conta exige saldo zero e nenhuma fatura aberta.
    Ao encerrar, todos os cartões da conta são cancelados.
    """
    conta = obter_conta_por_id(db, conta_id)

    if conta.estado == EstadoConta.ENCERRADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A conta já se encontra encerrada.",
        )

    # 1. Saldo deve ser exatamente zero
    if conta.saldo != Decimal("0.00"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"O encerramento de conta exige saldo zero. Saldo atual: R$ {conta.saldo:.2f}.",
        )

    # 2. Nenhuma fatura aberta ou atrasada vinculada a cartões da conta
    faturas_pendentes = (
        db.query(Fatura)
        .join(Cartao, Cartao.id == Fatura.cartao_id)
        .filter(
            Cartao.conta_id == conta.id,
            Fatura.estado.in_([EstadoFatura.ABERTA, EstadoFatura.ATRASADA]),
        )
        .all()
    )
    if faturas_pendentes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Não é possível encerrar a conta: existem {len(faturas_pendentes)} fatura(s) aberta(s) ou em atraso nos cartões associados.",
        )

    # 3. Cancelar todos os cartões vinculados à conta
    cartoes = db.query(Cartao).filter(Cartao.conta_id == conta.id).all()
    for cartao in cartoes:
        cartao.estado = EstadoCartao.CANCELADO

    # 4. Definir estado da conta como encerrada
    conta.estado = EstadoConta.ENCERRADA
    db.commit()
    db.refresh(conta)
    return conta
