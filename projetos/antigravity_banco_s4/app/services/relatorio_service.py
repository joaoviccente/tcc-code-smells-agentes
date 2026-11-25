from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.transacao import Transacao
from app.models.conta import Conta
from app.models.cliente import Cliente
from app.models.tarifa import Tarifa
from app.models.enums import EstadoTransacao, EstadoTarifa, CategoriaCliente
from app.schemas.relatorio import (
    RelatorioMaiorMovimentacaoResponse,
    ClienteMovimentacaoItem,
    RelatorioContasNegativasResponse,
    ContaSaldoNegativoItem,
    RelatorioReceitaTarifasResponse,
    ReceitaCategoriaItem,
)


class RelatorioService:
    @staticmethod
    def clientes_maior_movimentacao(
        db: Session,
        data_inicio: Optional[datetime] = None,
        data_fim: Optional[datetime] = None,
        limit: int = 10,
    ) -> RelatorioMaiorMovimentacaoResponse:
        """
        Relatório de clientes com maior volume de movimentação financeira no período especificado.
        Considera depósitos, saques e transferências efetivadas.
        """
        # Buscar todas as transações efetivadas no período
        query = db.query(Transacao).filter(Transacao.estado == EstadoTransacao.EFETIVADA)
        if data_inicio:
            query = query.filter(Transacao.data >= data_inicio)
        if data_fim:
            query = query.filter(Transacao.data <= data_fim)

        transacoes = query.all()

        # Agrupar movimentações por cliente
        movimentacao_por_cliente: Dict[int, Dict] = {}

        for t in transacoes:
            valor = Decimal(str(t.valor))

            # Transação associada à conta de origem
            if t.conta_id:
                conta = db.query(Conta).filter(Conta.id == t.conta_id).first()
                if conta and conta.cliente_id:
                    cid = conta.cliente_id
                    if cid not in movimentacao_por_cliente:
                        movimentacao_por_cliente[cid] = {
                            "total": Decimal("0.00"),
                            "count": 0,
                            "cliente": conta.cliente,
                        }
                    movimentacao_por_cliente[cid]["total"] += valor
                    movimentacao_por_cliente[cid]["count"] += 1

            # Se for transferência, a conta destino também movimentou valor
            if t.conta_destino_id and t.conta_destino_id != t.conta_id:
                conta_dest = db.query(Conta).filter(Conta.id == t.conta_destino_id).first()
                if conta_dest and conta_dest.cliente_id and conta_dest.cliente_id != conta.cliente_id:
                    cid_dest = conta_dest.cliente_id
                    if cid_dest not in movimentacao_por_cliente:
                        movimentacao_por_cliente[cid_dest] = {
                            "total": Decimal("0.00"),
                            "count": 0,
                            "cliente": conta_dest.cliente,
                        }
                    movimentacao_por_cliente[cid_dest]["total"] += valor
                    movimentacao_por_cliente[cid_dest]["count"] += 1

        # Ordenar por total movimentado desc
        ordenados = sorted(
            movimentacao_por_cliente.values(),
            key=lambda x: x["total"],
            reverse=True,
        )[:limit]

        itens = [
            ClienteMovimentacaoItem(
                cliente_id=item["cliente"].id,
                nome=item["cliente"].nome,
                cpf=item["cliente"].cpf,
                categoria=item["cliente"].categoria,
                situacao=item["cliente"].situacao,
                total_movimentado=item["total"],
                quantidade_transacoes=item["count"],
            )
            for item in ordenados
        ]

        return RelatorioMaiorMovimentacaoResponse(
            data_inicio=data_inicio,
            data_fim=data_fim,
            total_clientes_listados=len(itens),
            clientes=itens,
        )

    @staticmethod
    def contas_saldo_negativo(db: Session) -> RelatorioContasNegativasResponse:
        """
        Relatório de contas atualmente com saldo negativo.
        Inclui o cálculo da quantidade de dias em que a conta está negativa.
        """
        contas = db.query(Conta).filter(Conta.saldo < Decimal("0.00")).all()

        agora = datetime.utcnow()
        itens: List[ContaSaldoNegativoItem] = []
        valor_total = Decimal("0.00")

        for c in contas:
            saldo_dec = Decimal(str(c.saldo))
            valor_total += abs(saldo_dec)

            dias = 0
            if c.data_saldo_negativo_inicio:
                dias = (agora - c.data_saldo_negativo_inicio).days

            itens.append(
                ContaSaldoNegativoItem(
                    conta_id=c.id,
                    numero=c.numero,
                    cliente_id=c.cliente.id,
                    cliente_nome=c.cliente.nome,
                    cliente_cpf=c.cliente.cpf,
                    categoria_cliente=c.cliente.categoria,
                    saldo=saldo_dec,
                    limite_de_credito=c.limite_de_credito,
                    data_saldo_negativo_inicio=c.data_saldo_negativo_inicio,
                    dias_negativo=max(0, dias),
                    estado=c.estado,
                )
            )

        # Ordenar por saldo mais negativo
        itens.sort(key=lambda x: x.saldo)

        return RelatorioContasNegativasResponse(
            total_contas_negativas=len(itens),
            valor_total_negativo=valor_total,
            contas=itens,
        )

    @staticmethod
    def receita_tarifas_por_categoria(db: Session) -> RelatorioReceitaTarifasResponse:
        """
        Relatório de receita obtida com tarifas (cobradas) discriminadas por categoria de cliente.
        """
        # Inicializar dicionário para todas as categorias
        totais: Dict[str, Dict] = {
            cat.value: {"total": Decimal("0.00"), "count": 0}
            for cat in CategoriaCliente
        }

        # Tarifas cobradas com relacionamento para conta e cliente
        tarifas = (
            db.query(Tarifa)
            .join(Conta, Tarifa.conta_id == Conta.id)
            .join(Cliente, Conta.cliente_id == Cliente.id)
            .filter(Tarifa.estado == EstadoTarifa.COBRADA)
            .all()
        )

        receita_total = Decimal("0.00")
        total_cobradas = len(tarifas)

        for t in tarifas:
            cat_nome = t.conta.cliente.categoria.value
            valor = Decimal(str(t.valor))
            totais[cat_nome]["total"] += valor
            totais[cat_nome]["count"] += 1
            receita_total += valor

        itens = [
            ReceitaCategoriaItem(
                categoria=CategoriaCliente(cat_key),
                quantidade_tarifas=dados["count"],
                valor_total=dados["total"],
            )
            for cat_key, dados in totais.items()
        ]

        return RelatorioReceitaTarifasResponse(
            receita_total=receita_total,
            total_tarifas_cobradas=total_cobradas,
            receita_por_categoria=itens,
        )
