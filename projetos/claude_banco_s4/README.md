# API Banco – Contas Correntes

API REST em Python (FastAPI + SQLAlchemy 2) para gestão de clientes, contas, transações, cartões, faturas e tarifas.

## Execução

```bash
pip install -r requirements.txt
uvicorn banco.main:app --reload          # documentação interativa em http://localhost:8000/docs
python -m pytest -q                      # testes automatizados
```

Variáveis de ambiente:

| Variável | Padrão | Uso |
|---|---|---|
| `BANCO_DATABASE_URL` | `sqlite:///./banco.db` | Qualquer URL SQLAlchemy (ex.: `postgresql+psycopg://...`) |
| `BANCO_ROTINA_AUTOMATICA` | `1` | Executa o processamento diário na inicialização e periodicamente |
| `BANCO_INTERVALO_ROTINA_SEG` | `3600` | Intervalo da rotina automática |

Valores monetários são guardados como inteiros em centavos (tipo `Dinheiro`) e tratados como `Decimal`, sem erros de arredondamento de ponto flutuante.

## Endpoints

| Recurso | Endpoints |
|---|---|
| Clientes | `POST/GET /clientes`, `GET/PATCH/DELETE /clientes/{id}`, `GET /clientes/{id}/contas` |
| Contas | `POST/GET /contas`, `GET/PATCH /contas/{id}`, `DELETE /contas/{id}` (encerramento), `GET /contas/{id}/cartoes` |
| Cartões | `POST/GET /cartoes`, `GET/PATCH /cartoes/{id}`, `DELETE /cartoes/{id}` (cancelamento), `POST /cartoes/{id}/compras` |
| Transações | `POST /transacoes/deposito`, `/saque`, `/transferencia`, `POST /transacoes/{id}/estorno`, `GET /transacoes/{id}`, `GET /contas/{id}/extrato?inicio=&fim=` |
| Faturas | `GET /cartoes/{id}/faturas`, `GET /faturas/{id}`, `POST /faturas/{id}/pagamento` |
| Tarifas | `GET /contas/{id}/tarifas?estado=&tipo=&competencia=AAAA-MM` |
| Relatórios | `GET /relatorios/clientes-maior-movimentacao?inicio=&fim=&limite=`, `GET /relatorios/contas-saldo-negativo`, `GET /relatorios/receita-tarifas?inicio=&fim=` |
| Rotinas | `POST /rotinas/processamento-diario?data_referencia=AAAA-MM-DD` |

### Códigos HTTP

- `201` criação/operação registrada · `200` consulta/alteração · `204` remoção de cliente
- `404` recurso inexistente
- `409` conflito com o estado atual (conta não ativa, cliente bloqueado, CPF/e-mail duplicado, fatura já paga, encerramento com saldo ≠ 0 ou fatura em aberto…)
- `422` dados inválidos ou regra de negócio violada (saldo/limite insuficiente, limite diário/por transferência, prazo de estorno, valor de pagamento incorreto)

## Regras implementadas

Os parâmetros por categoria ficam em `banco/config.py`, exatamente como especificado (limites de R$ 1.000 / 5.000 / 20.000 de saque diário, R$ 5.000 / 50.000 / 200.000 por transferência, tarifa mensal de R$ 30 / 0 / 120, franquia de 3 / ilimitada / 50 transações e juros de 8% / 5% / 3% ao mês).

1. **Saque/transferência**: conta `ativa` e cliente `ativo`. O saque respeita o limite **diário acumulado** da categoria (soma dos saques efetivados no dia em todas as contas do cliente; saques estornados não contam). A transferência respeita o limite **por transferência**.
2. **Crédito**: o saldo pode ficar negativo até `-limite_credito`, e a operação mais a eventual tarifa precisam caber nesse limite.
3. **Tarifas por transação**: transferência entre contas do mesmo cliente fica isenta (registrada como `transferencia_mesmo_titular`) e não consome a franquia. Saques e transferências a terceiros consomem a franquia mensal da conta e, quando ela acaba, geram tarifa `cobrada`, debitada na hora.
4. **Estorno**: só de transação `efetivada` e em até 24 h. Reverte os saldos, marca a original como `estornada` e cria uma transação `estorno`.
5. **Faturas**: as compras entram na fatura `aberta` do mês. Virado o mês, a fatura passa a `fechada`, com vencimento no dia 10 do mês seguinte. Depois do vencimento fica `atrasada` e acumula juros simples pro rata (`valor × taxa × dias/30`). Com **mais de 10 dias** de atraso, o cartão é bloqueado. O pagamento precisa ser do valor total (valor + juros) e desbloqueia o cartão se não restar outro atraso.
6. **Saldo negativo há mais de 30 dias**: bloqueia o cliente e todos os cartões dele. A contagem recomeça quando o saldo volta a ser ≥ 0.
7. **Encerramento** (`DELETE /contas/{id}`): exige saldo zero e nenhuma fatura não paga com valor. Cancela todos os cartões da conta.

As transições que dependem do tempo (regras 5 e 6, tarifa mensal e nova tentativa de cobrar tarifas pendentes) rodam na **rotina diária**, que é idempotente. As faturas também são reavaliadas na hora em que são consultadas ou pagas.

## Premissas (pontos não definidos na especificação)

- **Valor da tarifa por transação excedente**: a especificação não informa. Adotei **R$ 2,50** (`TARIFA_POR_TRANSACAO` em `config.py`).
- **Tarifa mensal**: é gerada no primeiro processamento do mês, referente ao mês anterior, para contas que já existiam nele. Se não houver saldo/limite, fica `pendente` e a cobrança é tentada de novo nos processamentos seguintes. Para Premium, fica registrada como `isenta`.
- Depósito não consome franquia nem exige cliente ativo, para permitir regularizar o saldo. Exige apenas conta ativa.
- Estorno não devolve a tarifa já cobrada.
- Compras no cartão (`POST /cartoes/{id}/compras`) foram incluídas para que as faturas tenham valor. O pagamento da fatura é apenas registrado e não debita a conta, já que o modelo de transações não tem um tipo para isso.
- Conta poupança não aceita limite de crédito.
- Desbloquear um cliente bloqueado pela regra 6 é manual (`PATCH /clientes/{id}`).
