# API de Contas Correntes

API REST em Python (FastAPI + SQLAlchemy) para gestão de clientes, contas, transações, cartões, faturas e tarifas.

## Executar

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload          # documentação interativa em http://localhost:8000/docs
python -m pytest -q                    # testes
```

Banco padrão: SQLite (`banco.db`). Para outro SGBD relacional, defina `DATABASE_URL`
(ex.: `postgresql+psycopg://user:senha@host/banco`). As tabelas são criadas na inicialização.

## Estrutura

```
app/
  config.py        regras por categoria (limites, tarifas, franquias, juros)
  models.py        tabelas (SQLAlchemy) com CHECK constraints de domínio
  schemas.py       validação de entrada/saída (Pydantic; CPF com dígitos verificadores)
  services/        regras de negócio (transações, tarifas, faturas, rotinas, relatórios, cadastros)
  routers/         endpoints HTTP
  clock.py         relógio central (permite simular datas nos testes)
tests/             testes de ponta a ponta das regras 1–7
```

## Endpoints

| Recurso | Endpoints |
|---|---|
| Clientes | `POST/GET /clientes`, `GET/PATCH/DELETE /clientes/{id}` |
| Contas | `POST/GET /contas`, `GET/PATCH /contas/{id}`, `DELETE /contas/{id}` ou `POST /contas/{id}/encerramento` (encerra) |
| Extrato | `GET /contas/{id}/extrato?inicio=&fim=` |
| Tarifas | `GET /contas/{id}/tarifas?estado=&mes_referencia=` |
| Cartões | `POST/GET /cartoes`, `GET/PATCH /cartoes/{id}`, `DELETE /cartoes/{id}` (cancela) |
| Transações | `POST /transacoes/deposito`, `/saque`, `/transferencia`, `POST /transacoes/{id}/estorno`, `GET /transacoes/{id}` |
| Faturas | `GET/POST /cartoes/{id}/faturas`, `GET /faturas/{id}`, `POST /faturas/{id}/fechamento`, `POST /faturas/{id}/pagamento` |
| Rotina diária | `POST /rotinas/processamento` |
| Relatórios | `GET /relatorios/clientes-maior-movimentacao?inicio=&fim=&limite=`, `GET /relatorios/contas-saldo-negativo`, `GET /relatorios/receita-tarifas?inicio=&fim=` |

### Códigos HTTP

- `201` criação/operação registrada · `200` consulta/atualização · `204` exclusão de cliente
- `404` recurso inexistente
- `409` conflito de estado (conta/cliente bloqueado, conta encerrada, CPF/e-mail duplicado, fatura já paga, estorno repetido)
- `422` entrada inválida ou operação negada por regra (saldo/limite de crédito, limite diário, limite por transferência, prazo de estorno)

## Decisões e interpretações

- **Dinheiro**: `Decimal` em toda a aplicação, gravado como inteiro de centavos no banco (sem erro de ponto flutuante). Entradas com mais de 2 casas decimais são rejeitadas.
- **Limite diário de saque** (regra 1): soma dos saques efetivados no dia de calendário em **todas as contas do cliente** (saques estornados não contam). Transferências respeitam o **limite por transferência** da categoria.
- **Tarifa por transação** (regra 3): o enunciado não define o valor cobrado após esgotar a franquia; adotou-se **R$ 5,00**, configurável pela variável `TARIFA_POR_TRANSACAO`. Consomem franquia: saques e transferências para outro titular. Depósitos e estornos não consomem. A franquia é por conta e por mês. A tarifa entra no cálculo do limite de crédito (a operação é negada se valor + tarifa ultrapassar o limite). Usos da franquia ficam registrados como tarifa `isenta`.
- **Tarifa mensal**: gerada pela rotina diária uma vez por conta/mês. Sem saldo/limite suficiente fica `pendente` e é cobrada automaticamente no próximo crédito ou execução da rotina.
- **Estorno** (regra 4): até 24h após a transação; cria transação `estorno` e marca a original como `estornada`. É negado se a conta a ser debitada não tiver saldo/limite. A tarifa da transação original não é devolvida.
- **Faturas** (regra 5): vencimento padrão no dia 10 do mês seguinte ao de referência. Juros simples pro rata dia (taxa mensal × dias de atraso / 30). Cartão bloqueado com mais de 10 dias de atraso. O pagamento quita o total (valor + juros) debitando a conta do cartão. Situações são reavaliadas ao consultar faturas e na rotina diária.
- **Saldo negativo** (regra 6): a conta registra `negativo_desde`; com mais de 30 dias, cliente e todos os seus cartões são bloqueados (na rotina diária ou na próxima tentativa de saque/transferência). O cliente só pode ser reativado após regularizar o saldo.
- **Encerramento** (regra 7): "fatura aberta" = qualquer fatura não paga (aberta, fechada ou atrasada). Contas encerradas são mantidas para histórico.
- **Rotina diária**: `POST /rotinas/processamento` deve ser agendada (cron) uma vez por dia.
- O relatório de movimentação soma depósitos, saques e transferências efetivados (origem ou destino); estornados e estornos ficam de fora.
