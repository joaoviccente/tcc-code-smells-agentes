from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.cliente import CategoriaCliente, Cliente
from app.models.conta import Conta
from app.models.tarifa import EstadoTarifa, Tarifa
from app.models.transacao import EstadoTransacao, TipoTransacao, Transacao
from app.schemas.relatorio import (
    CategoriaReceitaItem,
    ClienteMovimentacaoItem,
    ContaSaldoNegativoItem,
    RelatorioContasSaldoNegativoResponse,
    RelatorioMovimentacaoResponse,
    RelatorioReceitaTarifasResponse,
)


class RelatorioService:
    @staticmethod
    def clientes_maior_movimentacao(
        db: Session,
        data_inicio: Optional[datetime] = None,
        data_fim: Optional[datetime] = None,
        limite: int = 10,
    ) -> RelatorioMovimentacaoResponse:
        """
        Relatório de clientes com maior movimentação no período especificado.
        Considera a soma de transações efetivadas (depósito, saque, transferência).
        """
        query = (
            db.query(
                Cliente.id.label("cliente_id"),
                Cliente.nome.label("nome"),
                Cliente.cpf.label("cpf"),
                Cliente.categoria.label("categoria"),
                func.coalesce(func.sum(Transacao.valor), Decimal("0.00")).label("total_movimentado"),
                func.count(Transacao.id).label("quantidade_transacoes"),
            )
            .join(Conta, Conta.cliente_id == Cliente.id)
            .join(Transacao, Transacao.conta_id == Conta.id)
            .filter(
                Transacao.estado == EstadoTransacao.EFETIVADA,
                Transacao.tipo.in_([
                    TipoTransacao.DEPOSITO,
                    TipoTransacao.SAQUE,
                    TipoTransacao.TRANSFERENCIA,
                ]),
            )
        )

        if data_inicio:
            query = query.filter(Transacao.data >= data_inicio)
        if data_fim:
            query = query.filter(Transacao.data <= data_fim)

        results = (
            query.group_by(Cliente.id, Cliente.nome, Cliente.cpf, Cliente.categoria)
            .order_by(func.sum(Transacao.valor).desc())
            .limit(limite)
            .all()
        )

        itens = [
            ClienteMovimentacaoItem(
                cliente_id=row.cliente_id,
                nome=row.nome,
                cpf=row.cpf,
                categoria=row.categoria,
                total_movimentado=Decimal(row.total_movimentado),
                quantidade_transacoes=row.quantidade_transacoes,
            )
            for row in results
        ]

        return RelatorioMovimentacaoResponse(
            data_inicio=data_inicio,
            data_fim=data_fim,
            total_clientes_listados=len(itens),
            clientes=itens,
        )

    @staticmethod
    def contas_com_saldo_negativo(db: Session) -> RelatorioContasSaldoNegativoResponse:
        """
        Relatório de contas que estão atualmente com saldo negativo,
        incluindo tempo de permanência em dias.
        """
        contas = (
            db.query(Conta)
            .join(Cliente, Conta.cliente_id == Cliente.id)
            .filter(Conta.saldo < Decimal("0.00"))
            .all()
        )

        agora = datetime.now(timezone.utc)
        itens = []
        for conta in contas:
            dias = 0
            if conta.data_saldo_negativo:
                dt_neg = (
                    conta.data_saldo_negativo
                    if conta.data_saldo_negativo.tzinfo is not None
                    else conta.data_saldo_negativo.replace(tzinfo=timezone.utc)
                )
                dias = (agora - dt_neg).days

            itens.append(
                ContaSaldoNegativoItem(
                    conta_id=conta.id,
                    numero=conta.numero,
                    cliente_id=conta.cliente.id,
                    cliente_nome=conta.cliente.nome,
                    cliente_cpf=conta.cliente.cpf,
                    categoria=conta.cliente.categoria,
                    saldo=conta.saldo,
                    limite_credito=conta.limite_credito,
                    data_saldo_negativo=conta.data_saldo_negativo,
                    dias_negativo=dias,
                )
            )

        return RelatorioContasSaldoNegativoResponse(
            total_contas_negativas=len(itens),
            contas=itens,
        )

    @staticmethod
    def receita_tarifas_por_categoria(db: Session) -> RelatorioReceitaTarifasResponse:
        """
        Relatório de receita obtida através de tarifas agrupada por categoria de cliente.
        """
        tarifas = (
            db.query(Tarifa, Cliente.categoria)
            .join(Conta, Tarifa.conta_id == Conta.id)
            .join(Cliente, Conta.cliente_id == Cliente.id)
            .all()
        )

        dados_por_cat = {
            cat: {
                "total_arrecadado": Decimal("0.00"),
                "cobradas": 0,
                "isentas": 0,
                "por_tipo": defaultdict(Decimal),
            }
            for cat in CategoriaCliente
        }

        total_geral = Decimal("0.00")

        for tarifa, categoria in tarifas:
            info = dados_por_cat[categoria]
            if tarifa.estado == EstadoTarifa.COBRADA:
                info["total_arrecadado"] += tarifa.valor
                info["cobradas"] += 1
                info["por_tipo"][tarifa.tipo] += tarifa.valor
                total_geral += tarifa.valor
            elif tarifa.estado == EstadoTarifa.ISENTA:
                info["isentas"] += 1

        itens = []
        for cat in CategoriaCliente:
            itens.append(
                CategoriaReceitaItem(
                    categoria=cat,
                    total_arrecadado=dados_por_cat[cat]["total_arrecadado"],
                    quantidade_tarifas_cobradas=dados_por_cat[cat]["cobradas"],
                    quantidade_tarifas_isentas=dados_por_cat[cat]["isentas"],
                    tarifas_por_tipo=dict(dados_por_cat[cat]["por_tipo"]),
                )
            )

        return RelatorioReceitaTarifasResponse(
            total_geral=total_geral,
            categorias=itens,
        )
