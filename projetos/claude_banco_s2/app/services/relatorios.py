from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.models import (
    CategoriaCliente, Cliente, Conta, EstadoTarifa, EstadoTransacao, Tarifa,
    TipoTransacao, Transacao,
)
from app.schemas import ContaNegativa, MovimentacaoCliente, ReceitaCategoria, ReceitaTarifas


def _intervalo(inicio: date | None, fim: date | None):
    ini = datetime.combine(inicio, time.min) if inicio else None
    fim_excl = datetime.combine(fim + timedelta(days=1), time.min) if fim else None
    return ini, fim_excl


def clientes_maior_movimentacao(db: Session, inicio: date | None, fim: date | None,
                                limite: int) -> list[MovimentacaoCliente]:
    """Soma o valor das transacoes efetivadas (deposito, saque, transferencia) em que o
    cliente participou como origem ou destino. Transacoes estornadas nao contam."""
    origem, destino = aliased(Conta), aliased(Conta)
    q = (
        select(Transacao.valor, origem.cliente_id, destino.cliente_id)
        .join(origem, Transacao.conta_id == origem.id)
        .outerjoin(destino, Transacao.conta_destino_id == destino.id)
        .where(
            Transacao.estado == EstadoTransacao.EFETIVADA,
            Transacao.tipo != TipoTransacao.ESTORNO,
        )
    )
    ini, fim_excl = _intervalo(inicio, fim)
    if ini:
        q = q.where(Transacao.data >= ini)
    if fim_excl:
        q = q.where(Transacao.data < fim_excl)

    total: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
    qtd: dict[int, int] = defaultdict(int)
    for valor, cli_origem, cli_destino in db.execute(q):
        participantes = {cli_origem} | ({cli_destino} if cli_destino else set())
        for cid in participantes:
            total[cid] += valor
            qtd[cid] += 1

    ranking = sorted(total, key=lambda c: (-total[c], c))[:limite]
    clientes = {c.id: c for c in db.scalars(select(Cliente).where(Cliente.id.in_(ranking)))}
    return [
        MovimentacaoCliente(
            cliente_id=cid, nome=clientes[cid].nome, categoria=clientes[cid].categoria,
            quantidade_transacoes=qtd[cid], valor_movimentado=total[cid],
        )
        for cid in ranking
    ]


def contas_saldo_negativo(db: Session, agora: datetime) -> list[ContaNegativa]:
    contas = db.scalars(select(Conta).where(Conta.saldo < 0).order_by(Conta.saldo, Conta.id))
    return [
        ContaNegativa(
            conta_id=c.id, numero=c.numero, cliente_id=c.cliente_id,
            cliente_nome=c.cliente.nome, categoria=c.cliente.categoria, saldo=c.saldo,
            limite_credito=c.limite_credito, negativo_desde=c.negativo_desde,
            dias_negativo=(agora - c.negativo_desde).days if c.negativo_desde else 0,
        )
        for c in contas
    ]


def receita_tarifas(db: Session, inicio: date | None, fim: date | None) -> ReceitaTarifas:
    q = (
        select(Tarifa.categoria, func.count(Tarifa.id), func.coalesce(func.sum(Tarifa.valor), 0))
        .where(Tarifa.estado == EstadoTarifa.COBRADA)
        .group_by(Tarifa.categoria)
    )
    ini, fim_excl = _intervalo(inicio, fim)
    if ini:
        q = q.where(Tarifa.cobrada_em >= ini)
    if fim_excl:
        q = q.where(Tarifa.cobrada_em < fim_excl)

    dados = {cat: (n, Decimal(s)) for cat, n, s in db.execute(q)}
    por_categoria = [
        ReceitaCategoria(
            categoria=cat,
            quantidade=dados.get(cat, (0, 0))[0],
            total=Decimal(dados.get(cat, (0, Decimal("0.00")))[1]).quantize(Decimal("0.01")),
        )
        for cat in CategoriaCliente
    ]
    return ReceitaTarifas(
        inicio=inicio, fim=fim, por_categoria=por_categoria,
        total_geral=sum((p.total for p in por_categoria), Decimal("0.00")),
    )
