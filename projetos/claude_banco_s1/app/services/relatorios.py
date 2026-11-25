from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CATEGORIAS, Cliente, Conta, Tarifa, Transacao
from app.services.comum import ZERO


def clientes_maior_movimentacao(db: Session, inicio: datetime, fim: datetime, limite: int) -> list[dict]:
    """Soma o valor das transacoes efetivadas (exclui estornadas e estornos) em que o cliente
    figura como origem ou destino. Transferencia entre contas do mesmo cliente conta uma vez."""
    transacoes = db.scalars(
        select(Transacao).where(
            Transacao.estado == "efetivada",
            Transacao.tipo != "estorno",
            Transacao.data >= inicio,
            Transacao.data <= fim,
        )
    ).all()
    total: dict[int, Decimal] = defaultdict(lambda: ZERO)
    quantidade: dict[int, int] = defaultdict(int)
    for t in transacoes:
        envolvidos = {t.conta.cliente_id}
        if t.conta_destino is not None:
            envolvidos.add(t.conta_destino.cliente_id)
        for cid in envolvidos:
            total[cid] += t.valor
            quantidade[cid] += 1
    ranking = sorted(total, key=lambda cid: (-total[cid], cid))[:limite]
    resultado = []
    for cid in ranking:
        cliente = db.get(Cliente, cid)
        resultado.append(
            {
                "cliente_id": cid,
                "nome": cliente.nome,
                "categoria": cliente.categoria,
                "quantidade_transacoes": quantidade[cid],
                "total_movimentado": total[cid],
            }
        )
    return resultado


def contas_saldo_negativo(db: Session, momento: datetime) -> list[dict]:
    contas = db.scalars(select(Conta).where(Conta.saldo < 0).order_by(Conta.saldo)).all()
    return [
        {
            "conta_id": c.id,
            "numero": c.numero,
            "cliente_id": c.cliente_id,
            "cliente_nome": c.cliente.nome,
            "saldo": c.saldo,
            "limite_credito": c.limite_credito,
            "negativo_desde": c.negativo_desde,
            "dias_negativo": (momento - c.negativo_desde).days if c.negativo_desde else 0,
        }
        for c in contas
    ]


def receita_tarifas_por_categoria(db: Session, inicio: datetime, fim: datetime) -> list[dict]:
    linhas = db.execute(
        select(Cliente.categoria, Tarifa.valor)
        .join(Conta, Conta.id == Tarifa.conta_id)
        .join(Cliente, Cliente.id == Conta.cliente_id)
        .where(Tarifa.estado == "cobrada", Tarifa.cobrada_em >= inicio, Tarifa.cobrada_em <= fim)
    ).all()
    receita = {c: ZERO for c in CATEGORIAS}
    quantidade = {c: 0 for c in CATEGORIAS}
    for categoria, valor in linhas:
        receita[categoria] += valor
        quantidade[categoria] += 1
    return [
        {"categoria": c, "quantidade_tarifas": quantidade[c], "receita": receita[c]} for c in CATEGORIAS
    ]
