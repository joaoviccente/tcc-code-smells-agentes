"""Configuracoes da aplicacao (sobrescreviveis por variaveis de ambiente)."""
import os
from decimal import Decimal

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banco.db")

# A especificacao nao define o valor da tarifa cobrada por transacao apos
# esgotada a franquia; o valor e configuravel aqui.
TARIFA_POR_TRANSACAO = Decimal(os.getenv("TARIFA_POR_TRANSACAO", "2.50"))

# Intervalo (segundos) do agendador interno que executa as rotinas
# (faturas atrasadas, bloqueios por saldo negativo, tarifas mensais).
# 0 desabilita o agendador.
INTERVALO_ROTINAS_SEGUNDOS = int(os.getenv("INTERVALO_ROTINAS_SEGUNDOS", "3600"))
