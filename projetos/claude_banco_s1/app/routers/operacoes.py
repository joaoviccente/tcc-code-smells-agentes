"""Transacoes, faturas, rotinas e relatorios."""
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app import clock
from app.database import get_db
from app.errors import RegraViolada
from app.models import Transacao
from app.schemas import (
    ClienteMovimentacao,
    ContaNegativa,
    DepositoEntrada,
    FaturaCriar,
    FaturaSaida,
    OperacaoSaida,
    ReceitaCategoria,
    RotinaSaida,
    SaqueEntrada,
    TransacaoSaida,
    TransferenciaEntrada,
)
from app.services import faturas, relatorios, rotinas, transacoes
from app.services.comum import obter

transacoes_router = APIRouter(prefix="/transacoes", tags=["Transacoes"])
faturas_router = APIRouter(tags=["Faturas"])
rotinas_router = APIRouter(prefix="/rotinas", tags=["Rotinas"])
relatorios_router = APIRouter(prefix="/relatorios", tags=["Relatorios"])


def _operacao(resultado) -> dict:
    transacao, tarifa, conta = resultado
    return {"transacao": transacao, "tarifa": tarifa, "saldo_conta": conta.saldo}


# ---------------- Transacoes ----------------
@transacoes_router.post("/deposito", response_model=OperacaoSaida, status_code=status.HTTP_201_CREATED)
def depositar(dados: DepositoEntrada, db: Session = Depends(get_db)):
    return _operacao(transacoes.depositar(db, dados.conta_id, dados.valor, dados.descricao, clock.agora()))


@transacoes_router.post("/saque", response_model=OperacaoSaida, status_code=status.HTTP_201_CREATED)
def sacar(dados: SaqueEntrada, db: Session = Depends(get_db)):
    return _operacao(transacoes.sacar(db, dados.conta_id, dados.valor, dados.descricao, clock.agora()))


@transacoes_router.post("/transferencia", response_model=OperacaoSaida, status_code=status.HTTP_201_CREATED)
def transferir(dados: TransferenciaEntrada, db: Session = Depends(get_db)):
    return _operacao(
        transacoes.transferir(
            db, dados.conta_origem_id, dados.conta_destino_id, dados.valor, dados.descricao, clock.agora()
        )
    )


@transacoes_router.post("/{transacao_id}/estorno", response_model=OperacaoSaida, status_code=status.HTTP_201_CREATED)
def estornar(transacao_id: int, db: Session = Depends(get_db)):
    return _operacao(transacoes.estornar(db, transacao_id, clock.agora()))


@transacoes_router.get("/{transacao_id}", response_model=TransacaoSaida)
def obter_transacao(transacao_id: int, db: Session = Depends(get_db)):
    return obter(db, Transacao, transacao_id, "Transacao")


# ---------------- Faturas ----------------
@faturas_router.get("/cartoes/{cartao_id}/faturas", response_model=list[FaturaSaida])
def listar_faturas(cartao_id: int, db: Session = Depends(get_db)):
    return faturas.listar_por_cartao(db, cartao_id, clock.agora())


@faturas_router.post(
    "/cartoes/{cartao_id}/faturas", response_model=FaturaSaida, status_code=status.HTTP_201_CREATED
)
def criar_fatura(cartao_id: int, dados: FaturaCriar, db: Session = Depends(get_db)):
    return faturas.criar(db, cartao_id, dados.mes_referencia, dados.valor, dados.vencimento)


@faturas_router.get("/faturas/{fatura_id}", response_model=FaturaSaida)
def obter_fatura(fatura_id: int, db: Session = Depends(get_db)):
    return faturas.obter_atualizada(db, fatura_id, clock.agora())


@faturas_router.post("/faturas/{fatura_id}/fechamento", response_model=FaturaSaida)
def fechar_fatura(fatura_id: int, db: Session = Depends(get_db)):
    return faturas.fechar(db, fatura_id, clock.agora())


@faturas_router.post("/faturas/{fatura_id}/pagamento", response_model=FaturaSaida)
def pagar_fatura(fatura_id: int, db: Session = Depends(get_db)):
    """Registra o pagamento do total devido (valor + juros), debitado da conta do cartao."""
    return faturas.pagar(db, fatura_id, clock.agora())


# ---------------- Rotinas ----------------
@rotinas_router.post("/processamento", response_model=RotinaSaida)
def processar(db: Session = Depends(get_db)):
    """Rotina diaria (agendar via cron): atrasos/juros de faturas, bloqueios e tarifas mensais."""
    return rotinas.processar(db, clock.agora())


# ---------------- Relatorios ----------------
def _periodo(inicio: date | None, fim: date | None) -> tuple[datetime, datetime]:
    hoje = clock.agora().date()
    inicio = inicio or hoje.replace(day=1)
    fim = fim or hoje
    if inicio > fim:
        raise RegraViolada("Data inicial posterior a data final")
    return datetime.combine(inicio, time.min), datetime.combine(fim, time.max)


@relatorios_router.get("/clientes-maior-movimentacao", response_model=list[ClienteMovimentacao])
def clientes_maior_movimentacao(
    inicio: date | None = Query(default=None, description="Padrao: primeiro dia do mes corrente"),
    fim: date | None = Query(default=None, description="Padrao: hoje (inclusivo)"),
    limite: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    ini, fi = _periodo(inicio, fim)
    return relatorios.clientes_maior_movimentacao(db, ini, fi, limite)


@relatorios_router.get("/contas-saldo-negativo", response_model=list[ContaNegativa])
def contas_saldo_negativo(db: Session = Depends(get_db)):
    return relatorios.contas_saldo_negativo(db, clock.agora())


@relatorios_router.get("/receita-tarifas", response_model=list[ReceitaCategoria])
def receita_tarifas(
    inicio: date | None = Query(default=None),
    fim: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    ini, fi = _periodo(inicio, fim)
    return relatorios.receita_tarifas_por_categoria(db, ini, fi)
