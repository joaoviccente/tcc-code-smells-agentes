from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import CATEGORY_RULES
from app.models.cartao import Cartao, EstadoCartao
from app.models.conta import EstadoConta
from app.models.cliente import SituacaoCliente
from app.models.fatura import EstadoFatura, Fatura
from app.schemas.fatura import FaturaCreate, FaturaPagamento
from app.services.conta_service import ContaService


class FaturaService:
    @staticmethod
    def criar_fatura(db: Session, cartao_id: int, fatura_in: FaturaCreate) -> Fatura:
        cartao = db.query(Cartao).filter(Cartao.id == cartao_id).first()
        if not cartao:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cartão #{cartao_id} não encontrado.",
            )

        if cartao.estado == EstadoCartao.CANCELADO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível criar fatura para cartão cancelado.",
            )

        db_fatura = Fatura(
            cartao_id=cartao_id,
            mes_referencia=fatura_in.mes_referencia,
            valor=fatura_in.valor,
            valor_pago=Decimal("0.00"),
            juros_acumulados=Decimal("0.00"),
            data_vencimento=fatura_in.data_vencimento,
            estado=EstadoFatura.ABERTA,
        )
        db.add(db_fatura)
        db.commit()
        db.refresh(db_fatura)
        return db_fatura

    @staticmethod
    def obter_fatura(db: Session, fatura_id: int) -> Fatura:
        fatura = db.query(Fatura).filter(Fatura.id == fatura_id).first()
        if not fatura:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Fatura #{fatura_id} não encontrada.",
            )
        return fatura

    @staticmethod
    def listar_faturas_por_cartao(
        db: Session, cartao_id: int, estado: Optional[str] = None
    ) -> List[Fatura]:
        # Valida existência do cartão
        cartao = db.query(Cartao).filter(Cartao.id == cartao_id).first()
        if not cartao:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cartão #{cartao_id} não encontrado.",
            )
        query = db.query(Fatura).filter(Fatura.cartao_id == cartao_id)
        if estado:
            query = query.filter(Fatura.estado == estado)
        return query.order_by(Fatura.data_vencimento.desc()).all()

    @staticmethod
    def calcular_total_devido(fatura: Fatura) -> Decimal:
        return (fatura.valor + fatura.juros_acumulados) - fatura.valor_pago

    @staticmethod
    def registrar_pagamento(
        db: Session, fatura_id: int, pagamento_in: FaturaPagamento
    ) -> Fatura:
        fatura = FaturaService.obter_fatura(db, fatura_id)

        if fatura.estado == EstadoFatura.PAGA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta fatura já está integralmente paga.",
            )

        total_devido = FaturaService.calcular_total_devido(fatura)
        valor_pagamento = (
            pagamento_in.valor_pago if pagamento_in.valor_pago is not None else total_devido
        )

        if valor_pagamento <= Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O valor do pagamento deve ser maior que zero.",
            )

        # Se informado pagamento via débito em conta
        if pagamento_in.conta_id is not None:
            conta = ContaService.obter_conta(db, pagamento_in.conta_id)
            if conta.estado != EstadoConta.ATIVA:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A conta para pagamento deve estar ativa.",
                )
            if conta.cliente.situacao != SituacaoCliente.ATIVO:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="O titular da conta para pagamento está bloqueado.",
                )
            # Regra 2: Saldo pode ficar negativo até o limite de crédito
            saldo_disponivel = conta.saldo + conta.limite_credito
            if saldo_disponivel < valor_pagamento:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Saldo insuficiente na conta para pagamento. Disponível: R$ {saldo_disponivel:.2f}",
                )
            ContaService.ajustar_saldo_e_historico_negativo(conta, -valor_pagamento)

        fatura.valor_pago += valor_pagamento
        novo_saldo_devedor = (fatura.valor + fatura.juros_acumulados) - fatura.valor_pago

        if novo_saldo_devedor <= Decimal("0.00"):
            fatura.estado = EstadoFatura.PAGA
            fatura.data_pagamento = datetime.now(timezone.utc)

        db.commit()
        db.refresh(fatura)
        return fatura

    @staticmethod
    def atualizar_faturas_atrasadas(
        db: Session, data_referencia: Optional[date] = None
    ) -> dict:
        """
        Regra 5: Fatura não paga até o vencimento passa ao estado atrasada e acumula juros
        conforme a categoria. Após 10 dias de atraso, o cartão é bloqueado.
        """
        hoje = data_referencia or date.today()
        # Busca faturas não pagas com vencimento anterior a hoje
        faturas = (
            db.query(Fatura)
            .filter(
                Fatura.estado.in_([EstadoFatura.ABERTA, EstadoFatura.FECHADA, EstadoFatura.ATRASADA]),
                Fatura.data_vencimento < hoje,
            )
            .all()
        )

        faturas_atualizadas = 0
        cartoes_bloqueados = 0

        for fatura in faturas:
            dias_atraso = (hoje - fatura.data_vencimento).days
            if dias_atraso > 0:
                fatura.estado = EstadoFatura.ATRASADA
                
                # Obtém a categoria do cliente proprietário
                cliente = fatura.cartao.conta.cliente
                categoria_str = cliente.categoria.value if hasattr(cliente.categoria, "value") else str(cliente.categoria)
                regras = CATEGORY_RULES.get(categoria_str, CATEGORY_RULES["comum"])
                taxa_mensal = regras["taxa_juros_atraso_mensal"]

                # Juros pro-rata com base no mês comercial (30 dias)
                # juros = valor_original * taxa_mensal * (dias_atraso / 30)
                juros = (fatura.valor * taxa_mensal * Decimal(dias_atraso) / Decimal(30)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                fatura.juros_acumulados = juros
                faturas_atualizadas += 1

                # Se atraso for superior a 10 dias, bloqueia o cartão
                if dias_atraso > 10 and fatura.cartao.estado == EstadoCartao.ATIVO:
                    fatura.cartao.estado = EstadoCartao.BLOQUEADO
                    cartoes_bloqueados += 1

        db.commit()
        return {
            "faturas_processadas": len(faturas),
            "faturas_atualizadas": faturas_atualizadas,
            "cartoes_bloqueados": cartoes_bloqueados,
        }
