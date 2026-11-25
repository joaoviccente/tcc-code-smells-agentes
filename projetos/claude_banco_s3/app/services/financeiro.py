"""Faturas, tarifas e relatorios."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.errors import Conflito, RegraViolada
from app.models import (
    CategoriaCliente, Cartao, Cliente, Conta, EstadoCartao, EstadoConta, EstadoFatura, EstadoTarifa,
    EstadoTransacao, Fatura, SituacaoCliente, Tarifa, TipoTransacao, Transacao,
)
from app.regras import DIAS_ATRASO_BLOQUEIO_CARTAO
from app.services.base import obter
from app.services.rotinas import MOTIVO_FATURA_ATRASADA, atualizar_fatura, atualizar_faturas_do_cartao


# ======================= faturas =======================
def criar_fatura(db: Session, cartao_id: int, dados) -> Fatura:
    cartao = obter(db, Cartao, cartao_id, "cartao")
    if cartao.estado == EstadoCartao.CANCELADO:
        raise Conflito("cartao_cancelado", "Cartao cancelado nao recebe novas faturas.")
    if dados.valor > cartao.limite:
        raise RegraViolada("limite_cartao_excedido",
                           f"Valor da fatura excede o limite do cartao ({cartao.limite}).")
    if db.scalar(select(Fatura.id).where(Fatura.cartao_id == cartao.id,
                                         Fatura.mes_referencia == dados.mes_referencia)):
        raise Conflito("fatura_duplicada", f"Ja existe fatura para {dados.mes_referencia}.")
    fatura = Fatura(cartao_id=cartao.id, mes_referencia=dados.mes_referencia, valor_original=dados.valor,
                    juros=Decimal("0.00"), valor=dados.valor, data_vencimento=dados.data_vencimento,
                    estado=EstadoFatura.ABERTA)
    db.add(fatura)
    db.flush()
    atualizar_fatura(fatura, clock.agora().date())
    db.commit()
    return fatura


def listar_faturas(db: Session, cartao_id: int, estado=None):
    cartao = obter(db, Cartao, cartao_id, "cartao")
    atualizar_faturas_do_cartao(cartao, clock.agora().date())
    db.commit()
    faturas = cartao.faturas
    if estado:
        faturas = [f for f in faturas if f.estado == estado]
    return faturas


def obter_fatura(db: Session, fatura_id: int) -> Fatura:
    fatura = obter(db, Fatura, fatura_id, "fatura")
    atualizar_fatura(fatura, clock.agora().date())
    db.commit()
    return fatura


def fechar_fatura(db: Session, fatura_id: int) -> Fatura:
    fatura = obter_fatura(db, fatura_id)
    if fatura.estado != EstadoFatura.ABERTA:
        raise Conflito("fatura_nao_aberta", f"Fatura esta {fatura.estado.value}.")
    fatura.estado = EstadoFatura.FECHADA
    db.commit()
    return fatura


def pagar_fatura(db: Session, fatura_id: int, valor: Decimal) -> Fatura:
    momento = clock.agora()
    fatura = obter_fatura(db, fatura_id)  # atualiza atraso/juros antes de pagar
    if fatura.estado == EstadoFatura.PAGA:
        raise Conflito("fatura_ja_paga", "Fatura ja esta paga.")
    if valor != fatura.valor:
        raise RegraViolada("valor_pagamento_divergente",
                           f"O pagamento deve ser do valor integral devido: {fatura.valor}.")
    fatura.estado = EstadoFatura.PAGA
    fatura.data_pagamento = momento
    fatura.valor_pago = valor

    # Desbloqueia o cartao se o bloqueio decorria apenas de atraso ja quitado
    cartao = fatura.cartao
    hoje = momento.date()
    ainda_atrasado = any(
        f.estado == EstadoFatura.ATRASADA and (hoje - f.data_vencimento).days > DIAS_ATRASO_BLOQUEIO_CARTAO
        for f in cartao.faturas
    )
    if (cartao.estado == EstadoCartao.BLOQUEADO and cartao.motivo_bloqueio == MOTIVO_FATURA_ATRASADA
            and not ainda_atrasado and cartao.conta.cliente.situacao == SituacaoCliente.ATIVO):
        cartao.estado = EstadoCartao.ATIVO
        cartao.motivo_bloqueio = None
    db.commit()
    return fatura


# ======================= tarifas =======================
def listar_tarifas(db: Session, conta_id: int, estado=None, competencia=None):
    obter(db, Conta, conta_id, "conta")
    q = select(Tarifa).where(Tarifa.conta_id == conta_id)
    if estado:
        q = q.where(Tarifa.estado == estado)
    if competencia:
        q = q.where(Tarifa.competencia == competencia)
    return db.scalars(q.order_by(Tarifa.criado_em, Tarifa.id)).all()


# ======================= relatorios =======================
def _intervalo(data_inicio: date, data_fim: date) -> tuple[datetime, datetime]:
    if data_inicio > data_fim:
        raise RegraViolada("periodo_invalido", "data_inicio deve ser anterior ou igual a data_fim.")
    return datetime.combine(data_inicio, time.min), datetime.combine(data_fim + timedelta(days=1), time.min)


def clientes_maior_movimentacao(db: Session, data_inicio: date, data_fim: date, limite: int):
    """Volume movimentado (depositos, saques e transferencias efetivadas, enviadas
    ou recebidas). Transacoes estornadas e os proprios estornos nao contam."""
    ini, fim = _intervalo(data_inicio, data_fim)
    filtros = (
        Transacao.estado == EstadoTransacao.EFETIVADA,
        Transacao.tipo.in_([TipoTransacao.DEPOSITO, TipoTransacao.SAQUE, TipoTransacao.TRANSFERENCIA]),
        Transacao.data >= ini, Transacao.data < fim,
    )
    totais: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
    qtd: dict[int, int] = defaultdict(int)
    for coluna in (Transacao.conta_id, Transacao.conta_destino_id):
        linhas = db.execute(
            select(Conta.cliente_id, Transacao.valor).join(Conta, Conta.id == coluna).where(*filtros)
        ).all()
        for cliente_id, valor in linhas:
            totais[cliente_id] += valor
            qtd[cliente_id] += 1
    ranking = sorted(totais.items(), key=lambda kv: (-kv[1], kv[0]))[:limite]
    resultado = []
    for cliente_id, total in ranking:
        c = db.get(Cliente, cliente_id)
        resultado.append({"cliente_id": c.id, "nome": c.nome, "cpf": c.cpf, "categoria": c.categoria,
                          "quantidade_transacoes": qtd[cliente_id], "total_movimentado": total})
    return resultado


def contas_saldo_negativo(db: Session):
    agora = clock.agora()
    contas = db.scalars(
        select(Conta).where(Conta.saldo < 0, Conta.estado != EstadoConta.ENCERRADA).order_by(Conta.saldo, Conta.id)
    ).all()
    return [{
        "conta_id": c.id, "numero": c.numero, "cliente_id": c.cliente_id, "cliente_nome": c.cliente.nome,
        "categoria": c.cliente.categoria, "saldo": c.saldo, "limite_credito": c.limite_credito,
        "estado": c.estado, "negativo_desde": c.negativo_desde,
        "dias_negativo": (agora - c.negativo_desde).days if c.negativo_desde else 0,
    } for c in contas]


def receita_tarifas_por_categoria(db: Session, data_inicio: date, data_fim: date):
    ini, fim = _intervalo(data_inicio, data_fim)
    # Valores armazenados em centavos inteiros: a soma no banco e exata.
    linhas = db.execute(
        select(Tarifa.categoria_cliente, func.count(Tarifa.id), func.sum(Tarifa.valor))
        .where(Tarifa.estado == EstadoTarifa.COBRADA, Tarifa.cobrado_em >= ini, Tarifa.cobrado_em < fim)
        .group_by(Tarifa.categoria_cliente)
    ).all()
    soma = {c: Decimal("0.00") for c in CategoriaCliente}
    qtd = {c: 0 for c in CategoriaCliente}
    for categoria, n, total in linhas:
        soma[CategoriaCliente(categoria)] = total or Decimal("0.00")
        qtd[CategoriaCliente(categoria)] = n
    return {
        "data_inicio": data_inicio, "data_fim": data_fim, "total": sum(soma.values(), Decimal("0.00")),
        "por_categoria": [{"categoria": c, "quantidade_tarifas": qtd[c], "receita": soma[c]} for c in CategoriaCliente],
    }
