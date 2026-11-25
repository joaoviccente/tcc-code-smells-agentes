from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app import clock
from app import schemas as s
from app.database import get_db
from app.errors import RegraViolada
from app.models import EstadoFatura, EstadoTarifa, Transacao
from app.services import financeiro, rotinas
from app.services import transacoes as tx
from app.services.base import obter

transacoes = APIRouter(tags=["transacoes"])
faturas = APIRouter(tags=["faturas"])
tarifas = APIRouter(tags=["tarifas"])
relatorios = APIRouter(prefix="/relatorios", tags=["relatorios"])
rotinas_r = APIRouter(prefix="/rotinas", tags=["rotinas"])


def _operacao(resultado):
    t, tarifa, saldo = resultado
    return {"transacao": t, "tarifa": tarifa, "saldo_conta": saldo}


# ---------- transacoes ----------
@transacoes.post("/transacoes/deposito", response_model=s.OperacaoOut, status_code=status.HTTP_201_CREATED)
def deposito(dados: s.DepositoIn, db: Session = Depends(get_db)):
    return _operacao(tx.depositar(db, dados.conta_id, dados.valor, dados.descricao))


@transacoes.post("/transacoes/saque", response_model=s.OperacaoOut, status_code=status.HTTP_201_CREATED)
def saque(dados: s.SaqueIn, db: Session = Depends(get_db)):
    return _operacao(tx.sacar(db, dados.conta_id, dados.valor, dados.descricao))


@transacoes.post("/transacoes/transferencia", response_model=s.OperacaoOut, status_code=status.HTTP_201_CREATED)
def transferencia(dados: s.TransferenciaIn, db: Session = Depends(get_db)):
    return _operacao(tx.transferir(db, dados.conta_origem_id, dados.conta_destino_id, dados.valor, dados.descricao))


@transacoes.post("/transacoes/{transacao_id}/estorno", response_model=s.OperacaoOut,
                 status_code=status.HTTP_201_CREATED)
def estorno(transacao_id: int, dados: s.EstornoIn | None = None, db: Session = Depends(get_db)):
    return _operacao(tx.estornar(db, transacao_id, dados.motivo if dados else None))


@transacoes.get("/transacoes/{transacao_id}", response_model=s.TransacaoOut)
def obter_transacao(transacao_id: int, db: Session = Depends(get_db)):
    return obter(db, Transacao, transacao_id, "transacao")


@transacoes.get("/contas/{conta_id}/extrato", response_model=s.ExtratoOut)
def extrato(conta_id: int, data_inicio: date | None = None, data_fim: date | None = None,
            db: Session = Depends(get_db)):
    return tx.extrato(db, conta_id, data_inicio, data_fim)


# ---------- faturas ----------
@faturas.get("/cartoes/{cartao_id}/faturas", response_model=list[s.FaturaOut])
def listar_faturas(cartao_id: int, estado: EstadoFatura | None = None, db: Session = Depends(get_db)):
    return financeiro.listar_faturas(db, cartao_id, estado)


@faturas.post("/cartoes/{cartao_id}/faturas", response_model=s.FaturaOut, status_code=status.HTTP_201_CREATED)
def criar_fatura(cartao_id: int, dados: s.FaturaCreate, db: Session = Depends(get_db)):
    return financeiro.criar_fatura(db, cartao_id, dados)


@faturas.get("/faturas/{fatura_id}", response_model=s.FaturaOut)
def obter_fatura(fatura_id: int, db: Session = Depends(get_db)):
    return financeiro.obter_fatura(db, fatura_id)


@faturas.post("/faturas/{fatura_id}/fechamento", response_model=s.FaturaOut)
def fechar_fatura(fatura_id: int, db: Session = Depends(get_db)):
    return financeiro.fechar_fatura(db, fatura_id)


@faturas.post("/faturas/{fatura_id}/pagamento", response_model=s.FaturaOut)
def pagar_fatura(fatura_id: int, dados: s.PagamentoIn, db: Session = Depends(get_db)):
    return financeiro.pagar_fatura(db, fatura_id, dados.valor)


# ---------- tarifas ----------
@tarifas.get("/contas/{conta_id}/tarifas", response_model=list[s.TarifaOut])
def listar_tarifas(conta_id: int, estado: EstadoTarifa | None = None,
                   competencia: s.MesReferencia | None = None, db: Session = Depends(get_db)):
    return financeiro.listar_tarifas(db, conta_id, estado, competencia)


# ---------- relatorios ----------
@relatorios.get("/clientes-maior-movimentacao", response_model=list[s.MovimentacaoClienteOut])
def maior_movimentacao(data_inicio: date, data_fim: date, limite: int = Query(10, ge=1, le=100),
                       db: Session = Depends(get_db)):
    return financeiro.clientes_maior_movimentacao(db, data_inicio, data_fim, limite)


@relatorios.get("/contas-saldo-negativo", response_model=list[s.ContaNegativaOut])
def contas_negativas(db: Session = Depends(get_db)):
    return financeiro.contas_saldo_negativo(db)


@relatorios.get("/receita-tarifas", response_model=s.ReceitaTarifasOut)
def receita_tarifas(data_inicio: date, data_fim: date, db: Session = Depends(get_db)):
    return financeiro.receita_tarifas_por_categoria(db, data_inicio, data_fim)


# ---------- rotinas (para agendamento) ----------
@rotinas_r.post("/diaria", response_model=s.RotinaDiariaOut)
def rotina_diaria(db: Session = Depends(get_db)):
    """Marca faturas atrasadas e aplica juros, bloqueia cartoes com mais de 10 dias de
    atraso e bloqueia clientes com conta negativa ha mais de 30 dias."""
    return rotinas.rotina_diaria(db, clock.agora())


@rotinas_r.post("/tarifas-mensais", response_model=s.RotinaTarifasOut)
def tarifas_mensais(competencia: s.MesReferencia | None = None, db: Session = Depends(get_db)):
    """Gera (de forma idempotente) a tarifa mensal de cada conta nao encerrada."""
    agora = clock.agora()
    competencia = competencia or agora.strftime("%Y-%m")
    if competencia > agora.strftime("%Y-%m"):
        raise RegraViolada("competencia_futura", "Nao e possivel gerar tarifas de competencia futura.")
    return rotinas.rotina_tarifas_mensais(db, competencia, agora)
