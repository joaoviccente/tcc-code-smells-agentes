from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.cartao import Cartao, EstadoCartao
from app.models.cliente import Cliente
from app.models.conta import Conta, EstadoConta
from app.models.fatura import EstadoFatura
from app.schemas.conta import ContaCreate, ContaUpdate


class ContaService:
    @staticmethod
    def criar_conta(db: Session, conta_in: ContaCreate) -> Conta:
        # Verifica se o cliente existe
        cliente = db.query(Cliente).filter(Cliente.id == conta_in.cliente_id).first()
        if not cliente:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cliente #{conta_in.cliente_id} não encontrado.",
            )

        # Verifica duplicidade de número de conta
        if db.query(Conta).filter(Conta.numero == conta_in.numero).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
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

    @staticmethod
    def obter_conta(db: Session, conta_id: int) -> Conta:
        conta = db.query(Conta).filter(Conta.id == conta_id).first()
        if not conta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conta #{conta_id} não encontrada.",
            )
        return conta

    @staticmethod
    def listar_contas(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        cliente_id: Optional[int] = None,
        estado: Optional[str] = None,
    ) -> List[Conta]:
        query = db.query(Conta)
        if cliente_id is not None:
            query = query.filter(Conta.cliente_id == cliente_id)
        if estado is not None:
            query = query.filter(Conta.estado == estado)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def atualizar_conta(db: Session, conta_id: int, conta_in: ContaUpdate) -> Conta:
        conta = ContaService.obter_conta(db, conta_id)

        if conta_in.tipo is not None:
            conta.tipo = conta_in.tipo
        if conta_in.limite_credito is not None:
            conta.limite_credito = conta_in.limite_credito
        if conta_in.estado is not None:
            # Se for tentar encerrar por aqui, valida as regras
            if conta_in.estado == EstadoConta.ENCERRADA:
                ContaService.validar_regras_encerramento(conta)
            conta.estado = conta_in.estado

        db.commit()
        db.refresh(conta)
        return conta

    @staticmethod
    def validar_regras_encerramento(conta: Conta) -> None:
        """
        Regra 7: O encerramento de conta exige saldo zero e nenhuma fatura aberta.
        Ao encerrar, todos os cartões da conta são cancelados.
        """
        if conta.saldo != Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"O encerramento de conta exige saldo zero. Saldo atual: R$ {conta.saldo:.2f}",
            )

        for cartao in conta.cartoes:
            for fatura in cartao.faturas:
                if fatura.estado in (EstadoFatura.ABERTA, EstadoFatura.FECHADA, EstadoFatura.ATRASADA):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"O encerramento de conta exige nenhuma fatura aberta. Cartão #{cartao.numero} possui a fatura #{fatura.id} no estado '{fatura.estado.value}'.",
                    )

    @staticmethod
    def encerrar_conta(db: Session, conta_id: int) -> dict:
        conta = ContaService.obter_conta(db, conta_id)
        if conta.estado == EstadoConta.ENCERRADA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta conta já está encerrada.",
            )

        ContaService.validar_regras_encerramento(conta)

        # Cancela todos os cartões vinculados à conta
        cartoes_cancelados_count = 0
        for cartao in conta.cartoes:
            if cartao.estado != EstadoCartao.CANCELADO:
                cartao.estado = EstadoCartao.CANCELADO
                cartoes_cancelados_count += 1

        conta.estado = EstadoConta.ENCERRADA
        db.commit()
        db.refresh(conta)

        return {
            "mensagem": "Conta encerrada com sucesso e todos os seus cartões foram cancelados.",
            "conta": conta,
            "cartoes_cancelados": cartoes_cancelados_count,
        }

    @staticmethod
    def ajustar_saldo_e_historico_negativo(conta: Conta, delta: Decimal) -> None:
        """
        Ajusta o saldo da conta e atualiza o marcador de saldo negativo.
        Regra 6: Conta com saldo negativo por mais de 30 dias bloqueia o cliente e seus cartões.
        """
        novo_saldo = conta.saldo + delta
        conta.saldo = novo_saldo

        if novo_saldo < Decimal("0.00"):
            if conta.data_saldo_negativo is None:
                conta.data_saldo_negativo = datetime.now(timezone.utc)
        else:
            conta.data_saldo_negativo = None
