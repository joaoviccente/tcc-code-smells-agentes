from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.orm import Session

from app import clock
from app.database import get_db
from app.enums import CategoriaCliente, EstadoFatura, EstadoTarifa, TipoTarifa, TipoTransacao
from app.erros import RegraNegocio
from app.schemas import (
    ClienteMovimentacao, ContaNegativa, DepositoIn, EstornoIn, EstornoOut, ExtratoOut,
    FaturaCriar, FaturaOut, OperacaoOut, PagamentoFaturaIn, ProcessamentoDiarioOut,
    ReceitaTarifasOut, SaqueIn, TarifaOut, TarifasMensaisIn, TarifasMensaisOut, TransacaoOut,
    TransferenciaIn, validar_mes,
)
from app.servicos import faturas as fat
from app.servicos import processamento as proc
from app.servicos import relatorios as rel
from app.servicos import tarifas as tar
from app.servicos import transacoes as trx

transacoes = APIRouter(prefix="/transacoes", tags=["Transacoes"])
extratos = APIRouter(prefix="/contas", tags=["Transacoes"])
faturas = APIRouter(tags=["Faturas"])
tarifas = APIRouter(prefix="/contas", tags=["Tarifas"])
relatorios = APIRouter(prefix="/relatorios", tags=["Relatorios"])
processamentos = APIRouter(prefix="/processamentos", tags=["Processamentos"])


def _periodo(inicio: Optional[date], fim: Optional[date]):
    if inicio and fim and inicio > fim:
        raise RegraNegocio("Data inicial posterior a data final")
    ini = datetime.combine(inicio, time.min) if inicio else None
    fi = datetime.combine(fim, time.max) if fim else None
    return ini, fi


# ---------------------------------------------------------------- transacoes

@transacoes.post("/deposito", response_model=OperacaoOut, status_code=status.HTTP_201_CREATED)
def deposito(dados: DepositoIn, db: Session = Depends(get_db)):
    return trx.depositar(db, dados)


@transacoes.post("/saque", response_model=OperacaoOut, status_code=status.HTTP_201_CREATED)
def saque(dados: SaqueIn, db: Session = Depends(get_db)):
    return trx.sacar(db, dados)


@transacoes.post("/transferencia", response_model=OperacaoOut, status_code=status.HTTP_201_CREATED)
def transferencia(dados: TransferenciaIn, db: Session = Depends(get_db)):
    return trx.transferir(db, dados)


@transacoes.post("/{transacao_id}/estorno", response_model=EstornoOut,
                 status_code=status.HTTP_201_CREATED)
def estorno(transacao_id: int, dados: Optional[EstornoIn] = Body(default=None),
            db: Session = Depends(get_db)):
    return trx.estornar(db, transacao_id, dados.descricao if dados else None)


@transacoes.get("/{transacao_id}", response_model=TransacaoOut)
def obter_transacao(transacao_id: int, db: Session = Depends(get_db)):
    return trx.obter_transacao(db, transacao_id)


@extratos.get("/{conta_id}/extrato", response_model=ExtratoOut)
def extrato(conta_id: int, inicio: Optional[date] = None, fim: Optional[date] = None,
            tipo: Optional[TipoTransacao] = None, db: Session = Depends(get_db)):
    ini, fi = _periodo(inicio, fim)
    return trx.extrato(db, conta_id, ini, fi, tipo)


# ------------------------------------------------------------------- faturas

@faturas.get("/cartoes/{cartao_id}/faturas", response_model=list[FaturaOut])
def listar_faturas(cartao_id: int, estado: Optional[EstadoFatura] = None,
                   db: Session = Depends(get_db)):
    return fat.listar_faturas(db, cartao_id, estado)


@faturas.post("/cartoes/{cartao_id}/faturas", response_model=FaturaOut,
              status_code=status.HTTP_201_CREATED,
              summary="Lancar fatura do cartao para um mes de referencia")
def criar_fatura(cartao_id: int, dados: FaturaCriar, db: Session = Depends(get_db)):
    return fat.criar_fatura(db, cartao_id, dados)


@faturas.get("/faturas/{fatura_id}", response_model=FaturaOut)
def obter_fatura(fatura_id: int, db: Session = Depends(get_db)):
    return fat.consultar_fatura(db, fatura_id)


@faturas.post("/faturas/{fatura_id}/fechamento", response_model=FaturaOut)
def fechar_fatura(fatura_id: int, db: Session = Depends(get_db)):
    return fat.fechar_fatura(db, fatura_id)


@faturas.post("/faturas/{fatura_id}/pagamento", response_model=FaturaOut)
def pagar_fatura(fatura_id: int, dados: PagamentoFaturaIn, db: Session = Depends(get_db)):
    return fat.pagar_fatura(db, fatura_id, dados.valor)


# ------------------------------------------------------------------- tarifas

@tarifas.get("/{conta_id}/tarifas", response_model=list[TarifaOut])
def listar_tarifas(conta_id: int, estado: Optional[EstadoTarifa] = None,
                   tipo: Optional[TipoTarifa] = None,
                   mes_referencia: Optional[str] = Query(None, examples=["2026-11"]),
                   db: Session = Depends(get_db)):
    if mes_referencia:
        try:
            validar_mes(mes_referencia)
        except ValueError as e:
            raise RegraNegocio(str(e))
    return tar.listar_tarifas(db, conta_id, estado, tipo, mes_referencia)


# ---------------------------------------------------------------- relatorios

@relatorios.get("/clientes-maior-movimentacao", response_model=list[ClienteMovimentacao])
def maior_movimentacao(inicio: date, fim: date, limite: int = Query(10, ge=1, le=100),
                       db: Session = Depends(get_db)):
    ini, fi = _periodo(inicio, fim)
    return rel.clientes_maior_movimentacao(db, ini, fi, limite)


@relatorios.get("/contas-saldo-negativo", response_model=list[ContaNegativa])
def saldo_negativo(categoria: Optional[CategoriaCliente] = None, db: Session = Depends(get_db)):
    return rel.contas_saldo_negativo(db, clock.agora().date(), categoria)


@relatorios.get("/receita-tarifas", response_model=ReceitaTarifasOut)
def receita_tarifas(inicio: Optional[date] = None, fim: Optional[date] = None,
                    db: Session = Depends(get_db)):
    ini, fi = _periodo(inicio, fim)
    return rel.receita_tarifas(db, ini, fi)


# ------------------------------------------------------------- processamento

@processamentos.post("/diario", response_model=ProcessamentoDiarioOut,
                     summary="Rotina diaria: atraso/juros de faturas, bloqueios e cobranca de tarifas")
def diario(data_referencia: Optional[date] = None, db: Session = Depends(get_db)):
    agora = clock.agora()
    hoje = data_referencia or agora.date()
    if hoje > agora.date():
        raise RegraNegocio("Data de referencia nao pode estar no futuro")
    return proc.processar_diario(db, hoje, agora)


@processamentos.post("/tarifas-mensais", response_model=TarifasMensaisOut,
                     summary="Gera a tarifa mensal de todas as contas para o mes de referencia")
def tarifas_mensais(dados: TarifasMensaisIn, db: Session = Depends(get_db)):
    return tar.gerar_tarifas_mensais(db, dados.mes_referencia, clock.agora())
