from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.conta import Conta
from app.models.cliente import Cliente
from app.models.transacao import Transacao
from app.models.tarifa import Tarifa
from app.models.cartao import Cartao
from app.schemas.relatorio import (
    ClienteMovimentacaoResponse,
    ContaSaldoNegativoResponse,
    ReceitaTarifasCategoriaResponse,
)
from app.config import (
    CategoriaCliente,
    SituacaoCliente,
    EstadoTransacao,
    EstadoTarifa,
    EstadoCartao,
)


class RelatorioService:
    @staticmethod
    def clientes_maior_movimentacao(
        db: Session,
        data_inicio: Optional[datetime] = None,
        data_fim: Optional[datetime] = None,
        limit: int = 10,
    ) -> List[ClienteMovimentacaoResponse]:
        query = (
            db.query(
                Cliente.id.label("cliente_id"),
                Cliente.nome.label("nome"),
                Cliente.cpf.label("cpf"),
                Cliente.categoria.label("categoria"),
                func.coalesce(func.sum(Transacao.valor), 0).label("total_movimentado"),
                func.count(Transacao.id).label("quantidade_transacoes"),
            )
            .join(Conta, Conta.cliente_id == Cliente.id)
            .join(Transacao, Transacao.conta_id == Conta.id)
            .filter(Transacao.estado == EstadoTransacao.EFETIVADA)
        )

        if data_inicio:
            query = query.filter(Transacao.data >= data_inicio)
        if data_fim:
            query = query.filter(Transacao.data <= data_fim)

        results = (
            query.group_by(Cliente.id, Cliente.nome, Cliente.cpf, Cliente.categoria)
            .order_by(func.sum(Transacao.valor).desc())
            .limit(limit)
            .all()
        )

        relatorio = []
        for r in results:
            relatorio.append(
                ClienteMovimentacaoResponse(
                    cliente_id=r.cliente_id,
                    nome=r.nome,
                    cpf=r.cpf,
                    categoria=r.categoria,
                    total_movimentado=Decimal(str(r.total_movimentado)),
                    quantidade_transacoes=r.quantidade_transacoes,
                )
            )
        return relatorio

    @staticmethod
    def contas_saldo_negativo(db: Session) -> List[ContaSaldoNegativoResponse]:
        contas = db.query(Conta).filter(Conta.saldo < Decimal("0.00")).all()
        agora = datetime.now(timezone.utc)

        resultado = []
        for c in contas:
            dias_negativo = 0
            if c.saldo_negativo_desde:
                dt = c.saldo_negativo_desde
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dias_negativo = max(0, (agora - dt).days)

            resultado.append(
                ContaSaldoNegativoResponse(
                    conta_id=c.id,
                    numero=c.numero,
                    cliente_id=c.cliente.id,
                    cliente_nome=c.cliente.nome,
                    cliente_cpf=c.cliente.cpf,
                    saldo=c.saldo,
                    limite_credito=c.limite_credito,
                    saldo_negativo_desde=c.saldo_negativo_desde,
                    dias_negativo=dias_negativo,
                )
            )
        return resultado

    @staticmethod
    def receita_tarifas_categoria(db: Session) -> List[ReceitaTarifasCategoriaResponse]:
        # Inicializa para todas as categorias
        totais = {
            cat: {"quantidade": 0, "total": Decimal("0.00")}
            for cat in CategoriaCliente
        }

        query = (
            db.query(
                Cliente.categoria,
                func.count(Tarifa.id).label("qtd"),
                func.coalesce(func.sum(Tarifa.valor), 0).label("total"),
            )
            .join(Conta, Tarifa.conta_id == Conta.id)
            .join(Cliente, Conta.cliente_id == Cliente.id)
            .filter(Tarifa.estado == EstadoTarifa.COBRADA)
            .group_by(Cliente.categoria)
            .all()
        )

        for row in query:
            cat = row.categoria
            if cat in totais:
                totais[cat]["quantidade"] = row.qtd
                totais[cat]["total"] = Decimal(str(row.total))

        return [
            ReceitaTarifasCategoriaResponse(
                categoria=cat,
                quantidade_tarifas=totais[cat]["quantidade"],
                total_arrecadado=totais[cat]["total"],
            )
            for cat in CategoriaCliente
        ]

    @staticmethod
    def processar_saldo_negativo_30_dias(db: Session) -> int:
        """
        Regra 6: Conta com saldo negativo por mais de 30 dias bloqueia o cliente e todos os seus cartões.
        """
        contas = db.query(Conta).filter(
            Conta.saldo < Decimal("0.00"),
            Conta.saldo_negativo_desde.isnot(None),
        ).all()

        agora = datetime.now(timezone.utc)
        afetados = 0

        for conta in contas:
            dt = conta.saldo_negativo_desde
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            dias = (agora - dt).days
            if dias > 30:
                cliente = conta.cliente
                if cliente.situacao != SituacaoCliente.BLOQUEADO:
                    cliente.situacao = SituacaoCliente.BLOQUEADO
                    afetados += 1

                # Bloqueia todos os cartões vinculados a qualquer conta do cliente
                for c in cliente.contas:
                    for cartao in c.cartoes:
                        if cartao.estado != EstadoCartao.CANCELADO:
                            cartao.estado = EstadoCartao.BLOQUEADO

        if afetados > 0:
            db.commit()

        return afetados
