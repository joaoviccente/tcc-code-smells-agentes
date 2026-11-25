# API Bancaria - Contas Correntes

API REST em Python (FastAPI + SQLAlchemy 2) para gestao de clientes, contas, transacoes,
cartoes, faturas e tarifas. Persistencia em banco relacional (SQLite por padrao; qualquer
banco suportado pelo SQLAlchemy via `DATABASE_URL`, ex.: `postgresql+psycopg://...`).

## Executar

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload          # documentacao interativa em http://localhost:8000/docs
python -m pytest -q                    # testes automatizados
```

As tabelas sao criadas automaticamente na inicializacao.

## Estrutura

```
app/
  main.py            aplicacao, tratamento de erros -> HTTP
  database.py        engine/sessao (DATABASE_URL)
  models.py          entidades ORM (valores monetarios gravados em centavos, inteiros)
  schemas.py         validacao de entrada / formato de saida (Pydantic)
  regras.py          parametros por categoria (valores exatos da especificacao)
  enums.py, erros.py, clock.py
  servicos/          regras de negocio (cadastros, transacoes, tarifas, faturas,
                     relatorios, processamento)
  routers/           endpoints
tests/               testes de API cobrindo as regras 1 a 7
```

## Endpoints

| Metodo | Rota | Descricao |
|---|---|---|
| POST/GET | `/clientes` | criar / listar (filtros: categoria, situacao, cpf) |
| GET/PATCH/DELETE | `/clientes/{id}` | consultar / atualizar / remover (somente sem contas) |
| GET | `/clientes/{id}/contas` | contas do cliente |
| POST/GET | `/contas` | abrir / listar (filtros: cliente_id, estado) |
| GET/PATCH | `/contas/{id}` | consultar / alterar limite de credito ou estado (ativa/bloqueada) |
| DELETE ou POST | `/contas/{id}` ou `/contas/{id}/encerramento` | encerrar conta (regra 7) |
| POST/GET | `/cartoes` | emitir / listar (filtros: conta_id, estado) |
| GET/PATCH/DELETE | `/cartoes/{id}` | consultar / alterar limite ou estado / cancelar |
| POST | `/transacoes/deposito` | deposito |
| POST | `/transacoes/saque` | saque |
| POST | `/transacoes/transferencia` | transferencia |
| POST | `/transacoes/{id}/estorno` | estorno (regra 4) |
| GET | `/transacoes/{id}` | consultar transacao |
| GET | `/contas/{id}/extrato?inicio=&fim=&tipo=` | extrato da conta |
| GET | `/cartoes/{id}/faturas` | listar faturas do cartao |
| POST | `/cartoes/{id}/faturas` | lancar fatura de um mes de referencia |
| GET | `/faturas/{id}` | consultar fatura |
| POST | `/faturas/{id}/fechamento` | fechar fatura |
| POST | `/faturas/{id}/pagamento` | registrar pagamento |
| GET | `/contas/{id}/tarifas?estado=&tipo=&mes_referencia=` | tarifas da conta |
| GET | `/relatorios/clientes-maior-movimentacao?inicio=&fim=&limite=` | ranking de movimentacao |
| GET | `/relatorios/contas-saldo-negativo` | contas negativas (com dias no negativo) |
| GET | `/relatorios/receita-tarifas?inicio=&fim=` | receita de tarifas por categoria |
| POST | `/processamentos/diario` | rotina diaria (regras 5 e 6, cobranca de pendentes) |
| POST | `/processamentos/tarifas-mensais` | gera tarifa mensal (`{"mes_referencia":"2026-11"}`) |

## Codigos HTTP

- `201` criacao / operacao financeira efetivada; `200` consulta/alteracao; `204` remocao.
- `404` recurso inexistente.
- `409` conflito de estado: conta nao ativa, cliente bloqueado, CPF/e-mail duplicado,
  transacao ja estornada, encerramento com saldo ou fatura em aberto etc.
- `422` dados invalidos (CPF, e-mail, valores com mais de 2 casas, campos extras) ou violacao
  de regra de negocio (saldo insuficiente, limite diario/por transferencia, prazo de estorno,
  valor de pagamento incorreto).

Erros retornam `{"erro": "<codigo>", "detail": ...}`. Valores monetarios trafegam como
strings decimais (`"1000.00"`) para evitar imprecisao de ponto flutuante.

## Decisoes de interpretacao

1. **Limite diario de saque** e acumulado por **cliente** (todas as suas contas) no dia
   civil, somando saques efetivados (saques estornados liberam o limite). Transferencias
   seguem o **limite por transferencia** da categoria (por operacao).
2. **Credito**: `saldo - valor >= -limite_credito`. Conta poupanca nao admite limite de credito.
3. **Tarifas por transacao**: saques e transferencias para terceiros consomem a franquia
   mensal da categoria (contada por cliente, no mes civil); depositos e estornos nao.
   Transferencias entre contas do mesmo cliente sao isentas e nao consomem franquia.
   **A especificacao nao define o valor da tarifa apos a franquia**; adotou-se R$ 5,00
   (`TARIFA_POR_TRANSACAO` em `app/regras.py`). A tarifa e debitada na hora se couber no
   saldo + limite; senao fica `pendente` e e cobrada no proximo deposito/credito ou na rotina
   diaria. Transacoes dentro da franquia geram registro de tarifa `isenta` (valor 0).
   Tarifa mensal: comum R$ 30,00; empresarial R$ 120,00; premium registrada como `isenta`.
4. **Estorno**: somente transacao `efetivada` (nao estorno) com ate 24h. Reverte os saldos,
   marca a original como `estornada` e cria transacao `estorno`. Tarifas ja cobradas nao sao
   devolvidas.
5. **Faturas**: vencimento padrao dia 10 do mes seguinte ao de referencia. Apos o vencimento
   passam a `atrasada`, com juros simples pro rata die: `valor x taxa_mensal x dias/30`
   (8% comum, 5% premium, 3% empresarial), recalculados de forma idempotente. Com mais de
   10 dias de atraso, o cartao e bloqueado. O pagamento deve ser exatamente `valor + juros`.
6. **Saldo negativo por mais de 30 dias** (contado a partir de quando o saldo ficou negativo)
   bloqueia o cliente e todos os seus cartoes. O cliente so pode ser desbloqueado apos
   regularizar.
7. **Encerramento**: exige saldo zero e nenhuma fatura nao quitada (aberta, fechada ou
   atrasada) nos cartoes da conta; cancela todos os cartoes. A conta e mantida com estado
   `encerrada` (historico preservado).

As regras temporais (5 e 6) sao aplicadas pela rotina `POST /processamentos/diario` (a ser
agendada, ex.: cron diario) e tambem sob demanda: saque/transferencia verificam a regra 6 do
cliente, e consultas/pagamentos de faturas atualizam atraso e juros.
