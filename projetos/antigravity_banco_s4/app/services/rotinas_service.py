from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.fatura import Fatura
from app.models.conta import Conta
from app.models.cartao import Cartao
from app.models.enums import EstadoFatura, EstadoCartao, SituacaoCliente, EstadoConta
from app.services.fatura_service import FaturaService


class RotinasService:
    @staticmethod
    def processar_faturas_atrasadas(db: Session, data_referencia: Optional[date] = None) -> Dict[str, Any]:
        """
        Regra 5: Fatura não paga até o vencimento passa ao estado atrasada e acumula juros conforme a categoria.
        Após 10 dias de atraso, o cartão é bloqueado.
        """
        hoje = data_referencia or date.today()
        faturas = db.query(Fatura).filter(
            Fatura.estado.in_([EstadoFatura.ABERTA, EstadoFatura.FECHADA, EstadoFatura.ATRASADA]),
            Fatura.data_vencimento < hoje,
        ).all()

        faturas_atualizadas = 0
        cartoes_bloqueados_ids = []

        for fatura in faturas:
            cartao_antes = fatura.cartao.estado
            FaturaService.atualizar_fatura_e_cartao(db, fatura, data_base=hoje)
            faturas_atualizadas += 1
            if cartao_antes != EstadoCartao.BLOQUEADO and fatura.cartao.estado == EstadoCartao.BLOQUEADO:
                cartoes_bloqueados_ids.append(fatura.cartao_id)

        db.commit()

        return {
            "mensagem": "Processamento de faturas atrasadas concluído.",
            "data_referencia": str(hoje),
            "faturas_processadas": faturas_atualizadas,
            "cartoes_bloqueados_por_atraso": cartoes_bloqueados_ids,
        }

    @staticmethod
    def processar_contas_negativas(db: Session, data_referencia: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Regra 6: Conta com saldo negativo por mais de 30 dias bloqueia o cliente e todos os seus cartões.
        """
        agora = data_referencia or datetime.utcnow()
        limite_30_dias = agora - timedelta(days=30)

        # Buscar contas com saldo negativo
        contas_negativas = db.query(Conta).filter(
            Conta.saldo < Decimal("0.00"),
            Conta.estado != EstadoConta.ENCERRADA,
        ).all()

        clientes_bloqueados_ids = []
        cartoes_bloqueados_ids = []

        for conta in contas_negativas:
            # Se não tinha registrado a data de início, registra como agora
            if conta.data_saldo_negativo_inicio is None:
                conta.data_saldo_negativo_inicio = agora
                continue

            # Se o saldo negativo persiste há mais de 30 dias
            if conta.data_saldo_negativo_inicio <= limite_30_dias:
                cliente = conta.cliente
                if cliente.situacao != SituacaoCliente.BLOQUEADO:
                    cliente.situacao = SituacaoCliente.BLOQUEADO
                    clientes_bloqueados_ids.append(cliente.id)

                # Bloquear todos os cartões de todas as contas do cliente
                for c in cliente.contas:
                    for cartao in c.cartoes:
                        if cartao.estado == EstadoCartao.ATIVO:
                            cartao.estado = EstadoCartao.BLOQUEADO
                            cartoes_bloqueados_ids.append(cartao.id)

        db.commit()

        return {
            "mensagem": "Processamento de contas com saldo negativo concluído.",
            "data_referencia": str(agora),
            "contas_negativas_verificadas": len(contas_negativas),
            "clientes_bloqueados": list(set(clientes_bloqueados_ids)),
            "cartoes_bloqueados": list(set(cartoes_bloqueados_ids)),
        }
