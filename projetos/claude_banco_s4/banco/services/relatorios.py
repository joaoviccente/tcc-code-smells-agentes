from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from .. import clock
from ..enums import Categoria, EstadoConta, EstadoTarifa, EstadoTransacao, TipoTransacao
from ..models import Cliente, Conta, Tarifa, Transacao
from .comum import ZERO


def maior_movimentacao(db: Session, inicio: datetime, fim: datetime, limite: int) -> list[dict]:
    """Soma das transacoes efetivadas (deposito, saque, transferencia enviada ou recebida)
    das contas de cada cliente no periodo. Estornos e transacoes estornadas nao contam.
    Transferencia entre contas do proprio cliente conta uma unica vez."""
    origem = aliased(Conta)
    destino = aliased(Conta)
    rows = db.execute(
        select(Transacao.id, Transacao.valor, origem.cliente_id, destino.cliente_id)
        .join(origem, Transacao.conta_id == origem.id)
        .outerjoin(destino, Transacao.conta_destino_id == destino.id)
        .where(
            Transacao.estado == EstadoTransacao.EFETIVADA,
            Transacao.tipo != TipoTransacao.ESTORNO,
            Transacao.data >= inicio,
            Transacao.data <= fim,
        )
    ).all()
    acumulado: dict[int, dict] = {}
    for _, valor, cli_origem, cli_destino in rows:
        for cid in {cli_origem, cli_destino} - {None}:
            a = acumulado.setdefault(cid, {"quantidade_transacoes": 0, "total_movimentado": ZERO})
            a["quantidade_transacoes"] += 1
            a["total_movimentado"] += valor
    if not acumulado:
        return []
    clientes = {c.id: c for c in db.scalars(select(Cliente).where(Cliente.id.in_(acumulado)))}
    ranking = sorted(acumulado.items(), key=lambda kv: (-kv[1]["total_movimentado"], kv[0]))[:limite]
    return [
        {"cliente_id": cid, "nome": clientes[cid].nome, "categoria": clientes[cid].categoria, **dados}
        for cid, dados in ranking
    ]


def contas_negativas(db: Session) -> list[dict]:
    hoje = clock.agora().date()
    contas = db.scalars(
        select(Conta).where(Conta.saldo < 0, Conta.estado != EstadoConta.ENCERRADA).order_by(Conta.saldo)
    )
    return [
        {
            "conta_id": c.id,
            "numero": c.numero,
            "cliente_id": c.cliente_id,
            "nome_cliente": c.cliente.nome,
            "saldo": c.saldo,
            "limite_credito": c.limite_credito,
            "negativo_desde": c.negativo_desde,
            "dias_negativo": (hoje - c.negativo_desde.date()).days if c.negativo_desde else 0,
        }
        for c in contas
    ]


def receita_tarifas(db: Session, inicio: datetime | None, fim: datetime | None) -> list[dict]:
    """Receita de tarifas efetivamente cobradas, agrupada pela categoria atual do cliente."""
    q = (
        select(Cliente.categoria, func.count(Tarifa.id), func.sum(Tarifa.valor))
        .join(Conta, Tarifa.conta_id == Conta.id)
        .join(Cliente, Conta.cliente_id == Cliente.id)
        .where(Tarifa.estado == EstadoTarifa.COBRADA)
        .group_by(Cliente.categoria)
    )
    if inicio:
        q = q.where(Tarifa.data_cobranca >= inicio)
    if fim:
        q = q.where(Tarifa.data_cobranca <= fim)
    dados = {cat: (qtd, total) for cat, qtd, total in db.execute(q).all()}
    return [
        {
            "categoria": cat,
            "quantidade_tarifas": dados.get(cat, (0, ZERO))[0],
            "receita": dados.get(cat, (0, ZERO))[1] or ZERO,
        }
        for cat in Categoria
    ]
