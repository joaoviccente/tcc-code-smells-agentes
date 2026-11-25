from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import TARIFA_POR_TRANSACAO
from app.models import (
    Conta, EstadoConta, EstadoTarifa, Tarifa, TipoTarifa, Transacao,
)
from app.regras import REGRAS
from app.services.comum import competencia_de, movimentar_saldo, pode_debitar


def cobrar(tarifa: Tarifa, conta: Conta, agora: datetime) -> None:
    """Debita a tarifa se couber no saldo + limite; caso contrario fica pendente."""
    if pode_debitar(conta, tarifa.valor):
        movimentar_saldo(conta, -tarifa.valor, agora)
        tarifa.estado = EstadoTarifa.COBRADA
        tarifa.cobrada_em = agora
    else:
        tarifa.estado = EstadoTarifa.PENDENTE


def registrar_tarifa_transacao(
    db: Session, conta: Conta, transacao: Transacao, agora: datetime
) -> Tarifa:
    """Regra 3: consome a franquia mensal de transacoes isentas; esgotada, gera tarifa."""
    categoria = conta.cliente.categoria
    franquia = REGRAS[categoria].transacoes_isentas_mes
    competencia = competencia_de(agora)

    if franquia is None:
        isenta = True
    else:
        usadas = db.scalar(
            select(func.count(Tarifa.id)).where(
                Tarifa.conta_id == conta.id,
                Tarifa.tipo == TipoTarifa.TRANSACAO,
                Tarifa.competencia == competencia,
                Tarifa.estado == EstadoTarifa.ISENTA,
            )
        )
        isenta = usadas < franquia

    tarifa = Tarifa(
        conta_id=conta.id,
        tipo=TipoTarifa.TRANSACAO,
        categoria=categoria,
        competencia=competencia,
        transacao=transacao,
        criada_em=agora,
        valor=0 if isenta else TARIFA_POR_TRANSACAO,
        estado=EstadoTarifa.ISENTA if isenta else EstadoTarifa.PENDENTE,
    )
    db.add(tarifa)
    if not isenta:
        cobrar(tarifa, conta, agora)
    return tarifa


def gerar_tarifas_mensais(db: Session, competencia: str, agora: datetime) -> dict[str, int]:
    """Gera (idempotente) a tarifa mensal da competencia e tenta cobrar tarifas pendentes."""
    resultado = {"geradas": 0, "cobradas": 0, "isentas": 0, "pendentes": 0, "pendentes_recobradas": 0}

    # Re-tentativa de tarifas pendentes anteriores
    for tarifa in db.scalars(select(Tarifa).where(Tarifa.estado == EstadoTarifa.PENDENTE)).all():
        if tarifa.conta.estado == EstadoConta.ENCERRADA:
            continue
        cobrar(tarifa, tarifa.conta, agora)
        if tarifa.estado == EstadoTarifa.COBRADA:
            resultado["pendentes_recobradas"] += 1

    ja_tarifadas = set(
        db.scalars(
            select(Tarifa.conta_id).where(
                Tarifa.tipo == TipoTarifa.MENSAL, Tarifa.competencia == competencia
            )
        )
    )
    contas = db.scalars(select(Conta).where(Conta.estado != EstadoConta.ENCERRADA)).all()
    for conta in contas:
        if conta.id in ja_tarifadas:
            continue
        categoria = conta.cliente.categoria
        valor = REGRAS[categoria].tarifa_mensal
        tarifa = Tarifa(
            conta_id=conta.id, tipo=TipoTarifa.MENSAL, categoria=categoria,
            competencia=competencia, criada_em=agora, valor=valor,
            estado=EstadoTarifa.ISENTA if valor == 0 else EstadoTarifa.PENDENTE,
        )
        db.add(tarifa)
        resultado["geradas"] += 1
        if valor == 0:
            resultado["isentas"] += 1
            continue
        cobrar(tarifa, conta, agora)
        resultado["cobradas" if tarifa.estado == EstadoTarifa.COBRADA else "pendentes"] += 1
    return resultado
