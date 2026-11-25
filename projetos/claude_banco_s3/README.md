# API Banco – Gestao de Contas Correntes

FastAPI + SQLAlchemy 2 + banco relacional (SQLite por padrao; qualquer banco suportado
pelo SQLAlchemy via `DATABASE_URL`, ex.: `postgresql+psycopg://user:senha@host/banco`).

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload        # documentacao interativa em http://localhost:8000/docs
python -m pytest -q                  # testes das regras de negocio
```

## Estrutura

```
app/
  main.py            app, tratamento de erros, registro de rotas
  database.py        engine/sessao (DATABASE_URL)
  models.py          entidades ORM e enums de estado
  money.py           tipo monetario exato (Decimal <-> centavos inteiros no banco)
  regras.py          parametros por categoria (limites, tarifas, franquia, juros)
  schemas.py         validacao de entrada / formato de saida (Pydantic)
  services/          regras de negocio (cadastros, transacoes, financeiro, rotinas)
  routers/           endpoints HTTP
tests/test_api.py    testes cobrindo as regras 1 a 7 e os relatorios
```

## Endpoints

| Recurso | Endpoints |
|---|---|
| Clientes | `POST/GET /clientes`, `GET/PATCH/DELETE /clientes/{id}`, `GET /clientes/{id}/contas` |
| Contas | `POST/GET /contas`, `GET/PATCH /contas/{id}`, `DELETE /contas/{id}` (encerramento), `GET /contas/{id}/cartoes` |
| Cartoes | `POST/GET /cartoes`, `GET/PATCH /cartoes/{id}`, `DELETE /cartoes/{id}` (cancelamento) |
| Transacoes | `POST /transacoes/deposito`, `/saque`, `/transferencia`, `POST /transacoes/{id}/estorno`, `GET /transacoes/{id}`, `GET /contas/{id}/extrato?data_inicio&data_fim` |
| Faturas | `GET/POST /cartoes/{id}/faturas`, `GET /faturas/{id}`, `POST /faturas/{id}/fechamento`, `POST /faturas/{id}/pagamento` |
| Tarifas | `GET /contas/{id}/tarifas?estado&competencia` |
| Relatorios | `GET /relatorios/clientes-maior-movimentacao?data_inicio&data_fim&limite`, `GET /relatorios/contas-saldo-negativo`, `GET /relatorios/receita-tarifas?data_inicio&data_fim` |
| Rotinas | `POST /rotinas/diaria`, `POST /rotinas/tarifas-mensais?competencia=AAAA-MM` |

Valores monetarios sao recebidos como numero ou string com no maximo 2 casas decimais.

## Codigos HTTP

- `201` criacao / operacao financeira registrada; `200` leitura e atualizacao; `204` remocao de cliente.
- `404` recurso inexistente.
- `409` conflito com o estado do recurso (conta nao ativa, cliente bloqueado, CPF duplicado,
  encerramento com saldo ou faturas pendentes, fatura ja paga, estorno de transacao ja estornada).
- `422` dados invalidos (validacao) ou violacao de regra quantitativa (saldo insuficiente,
  limite diario/por transferencia, prazo de estorno, valor de pagamento divergente).

Erros de negocio retornam `{"erro": "<codigo>", "mensagem": "<descricao>"}`.

## Decisoes de interpretacao

- **Precisao**: valores sao `Decimal` na aplicacao e centavos inteiros no banco – sem erros de ponto flutuante.
- **Limite diario de saque** (regra 1): soma dos saques efetivados no dia de calendario em **todas as contas do
  cliente** (o limite e da categoria do cliente). Saques estornados deixam de contar. Transferencias respeitam o
  **limite por transferencia** da categoria.
- **Limite de credito** (regra 2): a operacao e negada se `saldo - (valor + tarifa) < -limite_credito`.
- **Franquia e tarifa** (regra 3): saques e transferencias para terceiros consomem a franquia mensal **da conta**;
  cada uma gera um registro de tarifa (`isenta` dentro da franquia, `cobrada` apos). Transferencias entre contas
  do mesmo cliente nao geram tarifa nem consomem franquia; depositos e estornos tambem nao.
  O enunciado nao fixa o valor da tarifa por transacao excedente: padrao **R$ 2,50**, configuravel via
  variavel de ambiente `TARIFA_POR_TRANSACAO`.
- **Tarifa mensal**: gerada por conta nao encerrada via `POST /rotinas/tarifas-mensais` (idempotente por
  competencia). Premium gera registro `isenta` de R$ 0,00. Sem saldo disponivel, fica `pendente` e e cobrada
  automaticamente no proximo credito na conta.
- **Estorno** (regra 4): ate 24h apos a transacao; aplica-se a deposito, saque e transferencia efetivados.
  A original passa a `estornada` e e criada uma transacao `estorno` vinculada. Estorno de deposito/transferencia
  tambem respeita o limite de credito da conta debitada. Tarifas ja cobradas nao sao devolvidas.
- **Faturas** (regra 5): criadas via `POST /cartoes/{id}/faturas` (o enunciado nao define a origem).
  Apos o vencimento, fatura nao paga fica `atrasada`; juros simples pro rata dia: `valor_original x taxa_mensal x
  dias_atraso / 30` (recalculado de forma idempotente). Com mais de 10 dias de atraso o cartao e bloqueado.
  O pagamento deve ser do valor integral atualizado; quitado o atraso, o cartao bloqueado por esse motivo e
  reativado.
- **Saldo negativo** (regra 6): a conta guarda `negativo_desde`; ao ultrapassar 30 dias negativa, cliente e
  todos os seus cartoes sao bloqueados. Voltar a saldo >= 0 zera a contagem.
- **Encerramento** (regra 7): exige saldo zero e nenhuma fatura nao paga (aberta, fechada ou atrasada);
  cancela todos os cartoes. A conta e mantida (exclusao logica) para preservar o historico.
- **Regras temporais**: avaliadas automaticamente quando os dados sao acessados/operados (listagem de faturas,
  saques, transferencias, pagamentos, encerramento) e, para todo o banco, por `POST /rotinas/diaria`
  (indicado para execucao agendada diariamente).
- **Movimentacao no periodo**: soma de depositos, saques e transferencias efetivados (enviadas e recebidas);
  transacoes estornadas e estornos nao contam.
- **Receita de tarifas**: tarifas `cobradas` no periodo, agrupadas pela categoria do cliente no momento da cobranca.
