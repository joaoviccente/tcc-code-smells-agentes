from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.models.cartao import Cartao, EstadoCartao
from app.models.cliente import SituacaoCliente
from app.models.conta import Conta
from app.services.fatura_service import FaturaService


class RotinaService:
    @staticmethod
    def processar_inadimplencia(
        db: Session, data_referencia: Optional[datetime] = None
    ) -> dict:
        """
        Executa as verificações das regras 5 e 6:
        - Regra 5: faturas vencidas -> atrasada + juros; > 10 dias de atraso -> bloqueia cartão.
        - Regra 6: conta com saldo negativo por mais de 30 dias -> bloqueia o cliente e todos os seus cartões.
        """
        agora = data_referencia or datetime.now(timezone.utc)
        hoje = agora.date()

        # 1. Processa Regra 5 (faturas atrasadas e bloqueio de cartão após 10 dias)
        resultado_faturas = FaturaService.atualizar_faturas_atrasadas(db, data_referencia=hoje)

        # 2. Processa Regra 6 (contas negativas há mais de 30 dias)
        contas_negativas = (
            db.query(Conta)
            .filter(Conta.saldo < 0, Conta.data_saldo_negativo.isnot(None))
            .all()
        )

        clientes_bloqueados = 0
        cartoes_bloqueados_por_conta_negativa = 0

        for conta in contas_negativas:
            dt_negativo = (
                conta.data_saldo_negativo
                if conta.data_saldo_negativo.tzinfo is not None
                else conta.data_saldo_negativo.replace(tzinfo=timezone.utc)
            )
            dias_negativo = (agora - dt_negativo).days

            if dias_negativo > 30:
                cliente = conta.cliente
                if cliente.situacao != SituacaoCliente.BLOQUEADO:
                    cliente.situacao = SituacaoCliente.BLOQUEADO
                    clientes_bloqueados += 1

                # Bloqueia todos os cartões de todas as contas do cliente
                for c in cliente.contas:
                    for cartao in c.cartoes:
                        if cartao.estado == EstadoCartao.ATIVO:
                            cartao.estado = EstadoCartao.BLOQUEADO
                            cartoes_bloqueados_por_conta_negativa += 1

        db.commit()

        return {
            "data_execucao": agora.isoformat(),
            "faturas": resultado_faturas,
            "saldo_negativo_30_dias": {
                "contas_analisadas": len(contas_negativas),
                "clientes_bloqueados": clientes_bloqueados,
                "cartoes_bloqueados": cartoes_bloqueados_por_conta_negativa,
            },
        }
