# API de contas bancárias

Requer Python 3.10 ou superior.

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app:app
```

A documentação interativa fica em `http://127.0.0.1:8000/docs`. A API cria o banco SQLite na primeira execução. A variável `BANCO_DB` permite indicar outro caminho para o arquivo.

## Rotas

| Método | Rota | Operação |
| --- | --- | --- |
| POST, GET | `/clientes`, `/contas`, `/cartoes` | Criar ou listar |
| GET, PUT, DELETE | `/clientes/{id}`, `/contas/{id}`, `/cartoes/{id}` | Consultar, substituir ou excluir |
| POST | `/transacoes/deposito`, `/transacoes/saque` | Movimentar com `conta_id` e `valor` |
| POST | `/transacoes/transferencia` | Transferir com `conta_id`, `destino_id` e `valor` |
| POST | `/transacoes/{id}/estorno` | Estornar uma movimentação |
| GET | `/contas/{id}/extrato`, `/contas/{id}/tarifas` | Consultar extrato ou tarifas |
| POST, GET | `/cartoes/{id}/faturas` | Registrar ou listar faturas |
| POST | `/faturas/{id}/pagamento` | Quitar a fatura com débito na conta do cartão |
| GET | `/relatorios/clientes-maior-movimentacao` | Ranking por `inicio` e `fim` inclusivos, com `limite` opcional |
| GET | `/relatorios/contas-saldo-negativo` | Listar contas com saldo negativo |
| GET | `/relatorios/receita-tarifas` | Somar tarifas cobradas por categoria, com `inicio` e `fim` opcionais |

Valores monetários nas respostas são strings decimais com duas casas. Datas usam ISO 8601 e os dias e meses bancários seguem UTC. As rotas retornam `201` ao criar registros, `204` ao excluir, `404` para registros inexistentes, `409` para conflitos de negócio e `422` para entradas inválidas.

## Convenções de negócio

- O limite diário acumula saques de todas as contas do cliente. Transferências têm limite por operação e a franquia mensal é compartilhada entre as contas do mesmo cliente. Estornos liberam o valor do saque no cálculo diário ou a transferência no cálculo da franquia.
- A tarifa por transferência excedente tem padrão de R$ 10,00 e pode ser configurada com `BANCO_TARIFA_TRANSFERENCIA`. A mensalidade incide por conta e é lançada após o fim da competência, com a categoria vigente no lançamento. Tarifas sem saldo ou crédito suficiente ficam pendentes. O estorno devolve a tarifa de transferência cobrada ou cancela a cobrança pendente.
- A criação de fatura recebe `mes_referencia` no formato `AAAA-MM`, `vencimento` no formato `AAAA-MM-DD` e `valor`. Os juros são simples e proporcionais aos dias de atraso, usando um mês de 30 dias. A rotina de manutenção roda na inicialização, a cada minuto enquanto a API está em execução e antes das operações.
- Excluir uma conta encerra a conta e cancela seus cartões. O encerramento exige a quitação de todas as faturas. Excluir um cartão o cancela. Um cliente com contas vinculadas é preservado para manter o histórico.
- O ranking soma os valores das transações efetivadas e atribui as transferências externas aos dois titulares. Uma transferência interna conta uma vez para o titular.
