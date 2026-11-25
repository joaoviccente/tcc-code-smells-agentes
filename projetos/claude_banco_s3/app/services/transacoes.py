from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import clock
from app.errors import Conflito, RegraViolada
from app.models import (
    Conta, EstadoConta, EstadoTarifa, EstadoTransacao, SituacaoCliente, Tarifa, TipoTarifa,
    TipoTransacao, Transacao,
)
from app.regras import PRAZO_ESTORNO_HORAS, TARIFA_POR_TRANSACAO, regra_de
from app.services.base import ajustar_saldo, garantir_saldo, obter
from app.services.rotinas import cobrar_tarifas_pendentes, verificar_saldo_negativo


# ---------- validacoes ----------
def _checar_bloqueio_tempo(db: Session, conta: Conta, momento: datetime) -> None:
    """Aplica a regra 6 antes da operacao; persiste o bloqueio mesmo que a operacao falhe."""
    if verificar_saldo_negativo(conta.cliente, momento):
        db.commit()


def _exigir_conta_operavel(conta: Conta) -> None:
    """Regra 1: conta ativa de cliente ativo."""
    if conta.estado != EstadoConta.ATIVA:
        raise Conflito("conta_nao_ativa", f"Conta {conta.numero} esta {conta.estado.value}.")
    if conta.cliente.situacao != SituacaoCliente.ATIVO:
        raise Conflito("cliente_bloqueado", f"Cliente {conta.cliente_id} esta bloqueado.")


def _exigir_nao_encerrada(conta: Conta) -> None:
    if conta.estado == EstadoConta.ENCERRADA:
        raise Conflito("conta_encerrada", f"Conta {conta.numero} esta encerrada.")


def _inicio_dia(momento: datetime) -> datetime:
    return datetime.combine(momento.date(), time.min)


def total_sacado_no_dia(db: Session, cliente_id: int, momento: datetime) -> Decimal:
    """Soma dos saques efetivados no dia (todas as contas do cliente)."""
    inicio = _inicio_dia(momento)
    valores = db.scalars(
        select(Transacao.valor).join(Conta, Conta.id == Transacao.conta_id).where(
            Conta.cliente_id == cliente_id,
            Transacao.tipo == TipoTransacao.SAQUE,
            Transacao.estado == EstadoTransacao.EFETIVADA,
            Transacao.data >= inicio,
            Transacao.data < inicio + timedelta(days=1),
        )
    ).all()
    return sum(valores, Decimal("0.00"))


# ---------- tarifa por transacao (regra 3) ----------
def _tarifa_prevista(db: Session, conta: Conta, momento: datetime) -> tuple[Decimal, EstadoTarifa]:
    regra = regra_de(conta.cliente.categoria)
    if regra.transacoes_isentas_mes is None:
        return Decimal("0.00"), EstadoTarifa.ISENTA
    usadas = db.scalar(
        select(func.count(Tarifa.id)).where(
            Tarifa.conta_id == conta.id,
            Tarifa.tipo == TipoTarifa.TRANSACAO,
            Tarifa.competencia == momento.strftime("%Y-%m"),
        )
    )
    if usadas < regra.transacoes_isentas_mes:
        return Decimal("0.00"), EstadoTarifa.ISENTA
    return TARIFA_POR_TRANSACAO, EstadoTarifa.COBRADA


def _registrar_tarifa(db: Session, conta: Conta, transacao: Transacao, valor: Decimal,
                      estado: EstadoTarifa, momento: datetime) -> Tarifa:
    tarifa = Tarifa(
        conta_id=conta.id, tipo=TipoTarifa.TRANSACAO, valor=valor, estado=estado,
        categoria_cliente=conta.cliente.categoria, competencia=momento.strftime("%Y-%m"),
        transacao_id=transacao.id, criado_em=momento,
        cobrado_em=momento if estado == EstadoTarifa.COBRADA else None,
    )
    if estado == EstadoTarifa.COBRADA:
        ajustar_saldo(conta, -valor, momento)
    db.add(tarifa)
    return tarifa


def _nova_transacao(db: Session, **kw) -> Transacao:
    t = Transacao(estado=EstadoTransacao.EFETIVADA, **kw)
    db.add(t)
    db.flush()
    return t


# ---------- operacoes ----------
def depositar(db: Session, conta_id: int, valor: Decimal, descricao: str | None):
    conta = obter(db, Conta, conta_id, "conta")
    _exigir_nao_encerrada(conta)
    momento = clock.agora()
    ajustar_saldo(conta, valor, momento)
    t = _nova_transacao(db, conta_id=conta.id, tipo=TipoTransacao.DEPOSITO, valor=valor,
                        data=momento, descricao=descricao)
    cobrar_tarifas_pendentes(db, conta, momento)
    db.commit()
    return t, None, conta.saldo


def sacar(db: Session, conta_id: int, valor: Decimal, descricao: str | None):
    conta = obter(db, Conta, conta_id, "conta")
    momento = clock.agora()
    _checar_bloqueio_tempo(db, conta, momento)
    _exigir_conta_operavel(conta)

    regra = regra_de(conta.cliente.categoria)
    sacado = total_sacado_no_dia(db, conta.cliente_id, momento)
    if sacado + valor > regra.limite_saque_diario:
        raise RegraViolada(
            "limite_diario_saque_excedido",
            f"Limite diario de saque da categoria {conta.cliente.categoria.value} e "
            f"{regra.limite_saque_diario}; ja sacado hoje: {sacado}.",
        )
    valor_tarifa, estado_tarifa = _tarifa_prevista(db, conta, momento)
    garantir_saldo(conta, valor + valor_tarifa)

    ajustar_saldo(conta, -valor, momento)
    t = _nova_transacao(db, conta_id=conta.id, tipo=TipoTransacao.SAQUE, valor=valor,
                        data=momento, descricao=descricao)
    tarifa = _registrar_tarifa(db, conta, t, valor_tarifa, estado_tarifa, momento)
    db.commit()
    return t, tarifa, conta.saldo


def transferir(db: Session, origem_id: int, destino_id: int, valor: Decimal, descricao: str | None):
    if origem_id == destino_id:
        raise RegraViolada("contas_iguais", "Conta de origem e destino devem ser diferentes.")
    origem = obter(db, Conta, origem_id, "conta")
    destino = obter(db, Conta, destino_id, "conta")
    momento = clock.agora()
    _checar_bloqueio_tempo(db, origem, momento)
    _exigir_conta_operavel(origem)
    _exigir_nao_encerrada(destino)

    regra = regra_de(origem.cliente.categoria)
    if valor > regra.limite_por_transferencia:
        raise RegraViolada(
            "limite_transferencia_excedido",
            f"Limite por transferencia da categoria {origem.cliente.categoria.value} e "
            f"{regra.limite_por_transferencia}.",
        )
    mesmo_titular = origem.cliente_id == destino.cliente_id
    if mesmo_titular:
        valor_tarifa, estado_tarifa = Decimal("0.00"), None
    else:
        valor_tarifa, estado_tarifa = _tarifa_prevista(db, origem, momento)
    garantir_saldo(origem, valor + valor_tarifa)

    ajustar_saldo(origem, -valor, momento)
    ajustar_saldo(destino, valor, momento)
    t = _nova_transacao(db, conta_id=origem.id, conta_destino_id=destino.id,
                        tipo=TipoTransacao.TRANSFERENCIA, valor=valor, data=momento, descricao=descricao)
    tarifa = None
    if not mesmo_titular:
        tarifa = _registrar_tarifa(db, origem, t, valor_tarifa, estado_tarifa, momento)
    cobrar_tarifas_pendentes(db, destino, momento)
    db.commit()
    return t, tarifa, origem.saldo


def estornar(db: Session, transacao_id: int, motivo: str | None):
    original = obter(db, Transacao, transacao_id, "transacao")
    if original.tipo == TipoTransacao.ESTORNO:
        raise RegraViolada("estorno_nao_estornavel", "Uma transacao de estorno nao pode ser estornada.")
    if original.estado != EstadoTransacao.EFETIVADA:
        raise Conflito("transacao_nao_efetivada",
                       f"Apenas transacoes efetivadas podem ser estornadas (estado: {original.estado.value}).")
    momento = clock.agora()
    if momento - original.data > timedelta(hours=PRAZO_ESTORNO_HORAS):
        raise RegraViolada("prazo_estorno_expirado",
                           f"O estorno so e permitido em ate {PRAZO_ESTORNO_HORAS} horas apos a transacao.")

    conta = original.conta
    destino = original.conta_destino
    _exigir_nao_encerrada(conta)
    if destino is not None:
        _exigir_nao_encerrada(destino)

    # Reversao dos efeitos no saldo
    if original.tipo == TipoTransacao.DEPOSITO:
        garantir_saldo(conta, original.valor)
        ajustar_saldo(conta, -original.valor, momento)
    elif original.tipo == TipoTransacao.SAQUE:
        ajustar_saldo(conta, original.valor, momento)
    else:  # transferencia
        garantir_saldo(destino, original.valor)
        ajustar_saldo(destino, -original.valor, momento)
        ajustar_saldo(conta, original.valor, momento)

    original.estado = EstadoTransacao.ESTORNADA
    t = _nova_transacao(db, conta_id=conta.id, conta_destino_id=original.conta_destino_id,
                        tipo=TipoTransacao.ESTORNO, valor=original.valor, data=momento,
                        descricao=motivo or f"Estorno da transacao {original.id}",
                        transacao_original_id=original.id)
    db.commit()
    return t, None, conta.saldo


# ---------- extrato ----------
def natureza(transacao: Transacao, conta_id: int) -> str:
    """Credito ou debito da transacao do ponto de vista da conta informada."""
    tipo = transacao.tipo
    if tipo == TipoTransacao.ESTORNO:
        base = transacao.transacao_original
        return "debito" if natureza(base, conta_id) == "credito" else "credito"
    if tipo == TipoTransacao.DEPOSITO:
        return "credito"
    if tipo == TipoTransacao.SAQUE:
        return "debito"
    return "debito" if transacao.conta_id == conta_id else "credito"


def extrato(db: Session, conta_id: int, data_inicio: date | None, data_fim: date | None) -> dict:
    conta = obter(db, Conta, conta_id, "conta")
    if data_inicio and data_fim and data_inicio > data_fim:
        raise RegraViolada("periodo_invalido", "data_inicio deve ser anterior ou igual a data_fim.")
    q = select(Transacao).where(or_(Transacao.conta_id == conta_id, Transacao.conta_destino_id == conta_id))
    if data_inicio:
        q = q.where(Transacao.data >= datetime.combine(data_inicio, time.min))
    if data_fim:
        q = q.where(Transacao.data < datetime.combine(data_fim + timedelta(days=1), time.min))
    transacoes = db.scalars(q.order_by(Transacao.data, Transacao.id)).all()

    lancamentos, cred, deb = [], Decimal("0.00"), Decimal("0.00")
    for t in transacoes:
        nat = natureza(t, conta_id)
        if nat == "credito":
            cred += t.valor
        else:
            deb += t.valor
        item = {c: getattr(t, c) for c in (
            "id", "conta_id", "conta_destino_id", "tipo", "valor", "data", "estado", "descricao",
            "transacao_original_id")}
        item["natureza"] = nat
        lancamentos.append(item)
    return {
        "conta_id": conta.id, "numero": conta.numero, "saldo_atual": conta.saldo,
        "data_inicio": data_inicio, "data_fim": data_fim,
        "total_creditos": cred, "total_debitos": deb, "lancamentos": lancamentos,
    }
