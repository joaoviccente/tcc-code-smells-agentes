# API Banco – Gestão de Contas Correntes

API REST em Python (FastAPI + SQLAlchemy) com persistência relacional (SQLite por padrão;
qualquer banco suportado pelo SQLAlchemy via `DATABASE_URL`).

## Executar

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
# documentação interativa: http://localhost:8000/docs
python -m pytest            # 26 testes
```

| Variável de ambiente | Padrão | Descrição |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./banco.db` | URL do banco relacional |
| `TARIFA_POR_TRANSACAO` | `2.50` | Tarifa por transação após esgotar a franquia (**não definida na especificação**) |
| `INTERVALO_ROTINAS_SEGUNDOS` | `3600` | Intervalo do agendador interno das rotinas (0 desliga) |

## Estrutura

```
app/
  models.py      entidades (tabelas) e enums
  regras.py      parâmetros por categoria (valores exatos da especificação)
  schemas.py     validação de entrada/saída (Pydantic)
  services/      regras de negócio
  routers/       endpoints HTTP
tests/           testes de ponta a ponta
```

Os valores monetários são gravados como **inteiros de centavos** e expostos como `Decimal`
(serializados em JSON como string, ex. `"1000.00"`). Assim não há erro de arredondamento.
A entrada aceita no máximo 2 casas decimais.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| POST/GET | `/clientes` | Cria / lista (filtros `categoria`, `situacao`, paginação) |
| GET/PATCH/DELETE | `/clientes/{id}` | Consulta / altera (nome, e-mail, categoria, situação) / exclui (só sem contas) |
| POST/GET | `/contas` | Abre / lista (filtros `cliente_id`, `estado`, `tipo`) |
| GET/PATCH | `/contas/{id}` | Consulta / altera limite de crédito e estado (ativa ⇄ bloqueada) |
| DELETE | `/contas/{id}` | **Encerra** a conta (regra 7) |
| GET | `/contas/{id}/extrato?inicio=&fim=` | Extrato com o efeito (+/−) de cada lançamento |
| GET | `/contas/{id}/tarifas?estado=&competencia=` | Tarifas da conta |
| POST | `/transacoes/depositos` · `/saques` · `/transferencias` | Operações |
| POST | `/transacoes/{id}/estorno` | Estorno (regra 4) |
| GET | `/transacoes/{id}` | Consulta |
| POST/GET | `/cartoes` | Emite / lista (filtros `conta_id`, `estado`) |
| GET/PATCH/DELETE | `/cartoes/{id}` | Consulta / altera limite e estado (ativo ⇄ bloqueado) / **cancela** |
| GET/POST | `/cartoes/{id}/faturas` | Lista faturas do cartão / lança fatura de um mês |
| GET | `/faturas/{id}` | Consulta fatura (já com juros atualizados) |
| POST | `/faturas/{id}/pagamento` | Registra pagamento (valor total = valor + juros) |
| GET | `/relatorios/clientes-maior-movimentacao?inicio=&fim=&limite=` | Ranking |
| GET | `/relatorios/contas-saldo-negativo` | Contas negativas e há quantos dias |
| GET | `/relatorios/receita-tarifas?inicio=&fim=` | Receita de tarifas cobradas por categoria |
| POST | `/rotinas/processamento-diario?data_referencia=` | Executa as regras temporais 5 e 6 |
| POST | `/rotinas/tarifas-mensais?competencia=AAAA-MM` | Gera a tarifa mensal (idempotente) |

### Códigos HTTP

- `201` criação/operação registrada · `200` consulta/alteração · `204` exclusão de cliente
- `404` recurso inexistente
- `409` conflito de estado (conta/cliente bloqueado, conta encerrada, CPF/e-mail duplicado,
  fatura já paga, encerramento com saldo ou fatura em aberto...)
- `422` entrada inválida (CPF, e-mail, valores, campos desconhecidos) ou regra de negócio
  violada (saldo/limite insuficiente, limite diário, prazo de estorno...)

## Interpretações adotadas

Pontos que a especificação deixa em aberto e como foram resolvidos:

1. **Limite diário de saque**: é acumulado **por cliente** (todas as suas contas), no dia
   corrente. Saques estornados não contam.
2. **Transferência**: o limite da categoria vale **por operação**, como diz a tabela.
3. **Franquia de transações isentas**: contada **por conta e por mês**. Consomem franquia os
   saques e as transferências para outro cliente. Depósitos e estornos não consomem. A
   transferência entre contas do mesmo cliente não gera tarifa e não consome franquia.
   Toda transação tarifável gera um registro de tarifa: `isenta` dentro da franquia e
   `cobrada` fora dela. Se o saldo + limite não cobrir a tarifa, ela fica `pendente` e a
   rotina mensal tenta cobrá-la de novo.
4. **Valor da tarifa por transação**: não foi especificado. O padrão é R$ 2,50, configurável.
5. **Tarifa mensal**: gerada por conta e por competência pela rotina. Para premium é
   registrada como `isenta`. O relatório de receita usa a categoria do cliente **no momento
   da cobrança**.
6. **Estorno**: permitido em até 24 h. Estorna depósito, saque ou transferência, mas não outro
   estorno. O estorno de um crédito também respeita o limite de crédito da conta debitada.
   A tarifa da transação original não é devolvida.
7. **Faturas**: a criação de faturas não está no escopo pedido. Como não há módulo de
   compras, o endpoint `POST /cartoes/{id}/faturas` lança o valor consolidado do mês.
   - O vencimento padrão é o dia 10 do mês seguinte.
   - A fatura `aberta` passa a `fechada` quando o mês de referência termina. Se não for paga
     até o vencimento, passa a `atrasada`.
   - Juros simples pró-rata: `valor × taxa_mensal × dias_atraso / 30`.
   - Com **mais de 10 dias** de atraso, o cartão é bloqueado (motivo `atraso_fatura`).
   - O pagamento deve ser **integral** (valor + juros) e reativa o cartão bloqueado por
     atraso.
8. **Saldo negativo > 30 dias**: a data em que o saldo ficou negativo é registrada em
   `negativo_desde`. Quando o prazo é excedido, o cliente e os cartões ativos dele são
   bloqueados. Isso acontece pela rotina e também no momento em que o cliente tenta uma
   operação. O cliente só pode ser reativado depois de regularizar o saldo. Ao ser
   reativado, os cartões bloqueados por esse motivo voltam a ficar ativos.
9. **Encerramento** (`DELETE /contas/{id}`): é uma exclusão lógica que mantém o histórico.
   Exige saldo zero e nenhuma fatura `aberta`, `fechada` ou `atrasada`. Cancela todos os
   cartões da conta.
10. **Poupança** não aceita limite de crédito. **Depósitos** são aceitos em contas
    bloqueadas, mas não em contas encerradas.
11. As regras temporais rodam pelo agendador interno, pelos endpoints `/rotinas/*` e também
    ao consultar ou pagar faturas.
