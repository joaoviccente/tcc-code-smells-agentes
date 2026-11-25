from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Cliente, Conta, Fatura
from app.services import faturas, tarifas
from app.services.comum import bloquear_cliente_e_cartoes, negativo_excedido


def processar(db: Session, momento: datetime) -> dict:
    """Rotina diaria: atrasos de fatura, bloqueios, tarifas mensais e cobranca de pendencias."""
    resultado = {
        "data_referencia": momento,
        "faturas_atrasadas": 0,
        "cartoes_bloqueados": 0,
        "clientes_bloqueados": 0,
        "tarifas_mensais_geradas": 0,
        "tarifas_pendentes_cobradas": 0,
    }

    # Regra 5 - faturas vencidas
    for fatura in db.scalars(select(Fatura).where(Fatura.estado.in_(faturas.EM_ABERTO))).all():
        passou, bloqueou = faturas.atualizar_situacao(fatura, momento)
        resultado["faturas_atrasadas"] += passou
        resultado["cartoes_bloqueados"] += bloqueou

    contas = db.scalars(select(Conta).where(Conta.estado != "encerrada")).all()

    # Tarifas mensais e cobranca de tarifas pendentes
    for conta in contas:
        if tarifas.gerar_tarifa_mensal(db, conta, momento) is not None:
            resultado["tarifas_mensais_geradas"] += 1
        resultado["tarifas_pendentes_cobradas"] += tarifas.cobrar_pendentes(db, conta, momento)

    # Regra 6 - saldo negativo por mais de 30 dias
    for cliente in db.scalars(select(Cliente).where(Cliente.situacao == "ativo")).all():
        if any(negativo_excedido(c, momento) for c in cliente.contas):
            resultado["cartoes_bloqueados"] += bloquear_cliente_e_cartoes(db, cliente)
            resultado["clientes_bloqueados"] += 1

    db.commit()
    return resultado
