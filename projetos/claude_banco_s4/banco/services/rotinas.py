"""Processamento diario: faturas (regra 5), saldo negativo (regra 6) e tarifas mensais."""
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import DIAS_SALDO_NEGATIVO_BLOQUEIO
from ..enums import (
    EstadoCartao,
    EstadoConta,
    EstadoFatura,
    EstadoTarifa,
    MotivoBloqueioCartao,
    SituacaoCliente,
    TipoTarifa,
)
from ..models import Cartao, Conta, Fatura, Tarifa
from .comum import ZERO, aplicar_movimento, competencia, regras_do_cliente
from .faturas import EVT_ATRASADA, EVT_CARTAO_BLOQUEADO, EVT_FECHADA, atualizar_situacao_fatura


def _mes_anterior(d: date) -> str:
    return competencia(date(d.year - 1, 12, 1) if d.month == 1 else date(d.year, d.month - 1, 1))


def processar(db: Session, hoje: date) -> dict:
    momento = datetime.combine(hoje, time.min)
    r = dict(
        data_referencia=hoje,
        faturas_fechadas=0,
        faturas_atrasadas=0,
        cartoes_bloqueados_por_atraso=0,
        clientes_bloqueados_por_saldo_negativo=0,
        cartoes_bloqueados_por_cliente=0,
        tarifas_mensais_geradas=0,
        tarifas_pendentes_cobradas=0,
    )

    # Regra 5 - fechamento, atraso, juros e bloqueio do cartao apos 10 dias
    for fatura in db.scalars(select(Fatura).where(Fatura.estado != EstadoFatura.PAGA)):
        eventos = atualizar_situacao_fatura(fatura, hoje)
        r["faturas_fechadas"] += EVT_FECHADA in eventos
        r["faturas_atrasadas"] += EVT_ATRASADA in eventos
        r["cartoes_bloqueados_por_atraso"] += EVT_CARTAO_BLOQUEADO in eventos

    # Regra 6 - conta negativa ha mais de 30 dias bloqueia cliente e todos os seus cartoes
    negativas = db.scalars(
        select(Conta).where(Conta.negativo_desde.is_not(None), Conta.estado != EstadoConta.ENCERRADA)
    )
    for conta in negativas:
        if (hoje - conta.negativo_desde.date()).days <= DIAS_SALDO_NEGATIVO_BLOQUEIO:
            continue
        cliente = conta.cliente
        if cliente.situacao != SituacaoCliente.BLOQUEADO:
            cliente.situacao = SituacaoCliente.BLOQUEADO
            r["clientes_bloqueados_por_saldo_negativo"] += 1
        cartoes = db.scalars(
            select(Cartao).join(Conta).where(Conta.cliente_id == cliente.id, Cartao.estado == EstadoCartao.ATIVO)
        )
        for cartao in cartoes:
            cartao.estado = EstadoCartao.BLOQUEADO
            cartao.motivo_bloqueio = MotivoBloqueioCartao.CLIENTE_BLOQUEADO
            r["cartoes_bloqueados_por_cliente"] += 1
    db.flush()

    # Tarifas pendentes: tenta cobrar novamente (mais antigas primeiro)
    pendentes = db.scalars(
        select(Tarifa).join(Conta)
        .where(Tarifa.estado == EstadoTarifa.PENDENTE, Conta.estado != EstadoConta.ENCERRADA)
        .order_by(Tarifa.data, Tarifa.id)
    )
    for tarifa in pendentes:
        if _tentar_cobrar(tarifa, momento):
            r["tarifas_pendentes_cobradas"] += 1

    # Tarifa mensal referente ao mes anterior, para contas existentes naquele mes
    comp = _mes_anterior(hoje)
    inicio_mes_atual = datetime(hoje.year, hoje.month, 1)
    contas = db.scalars(
        select(Conta).where(Conta.estado != EstadoConta.ENCERRADA, Conta.criado_em < inicio_mes_atual)
    )
    for conta in contas:
        ja_existe = db.scalar(
            select(Tarifa.id).where(
                Tarifa.conta_id == conta.id, Tarifa.tipo == TipoTarifa.MENSAL, Tarifa.competencia == comp
            )
        )
        if ja_existe:
            continue
        valor = regras_do_cliente(conta.cliente).tarifa_mensal
        tarifa = Tarifa(conta=conta, tipo=TipoTarifa.MENSAL, valor=valor, competencia=comp, data=momento,
                        estado=EstadoTarifa.PENDENTE, descricao=f"Tarifa mensal {comp}")
        if valor == ZERO:
            tarifa.estado = EstadoTarifa.ISENTA
            tarifa.descricao = f"Tarifa mensal {comp} - categoria isenta"
        else:
            _tentar_cobrar(tarifa, momento)
        db.add(tarifa)
        db.flush()
        r["tarifas_mensais_geradas"] += 1

    db.commit()
    return r


def _tentar_cobrar(tarifa: Tarifa, momento: datetime) -> bool:
    """Debita a tarifa se couber no saldo + limite de credito; senao permanece pendente."""
    conta = tarifa.conta
    if conta.saldo - tarifa.valor < -conta.limite_credito:
        tarifa.estado = EstadoTarifa.PENDENTE
        return False
    aplicar_movimento(conta, -tarifa.valor, momento)
    tarifa.estado = EstadoTarifa.COBRADA
    tarifa.data_cobranca = momento
    return True
