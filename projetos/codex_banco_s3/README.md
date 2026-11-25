# API de contas bancárias

Requer Python 3.10 ou superior. Na raiz do projeto:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app
```

A documentação interativa fica em http://127.0.0.1:8000/docs. O SQLite cria o
arquivo `banco.sqlite3` na primeira inicialização. A variável `BANCO_DB` permite
definir outro caminho. Envie valores monetários em reais, com até duas casas
decimais. A API devolve esses valores como strings decimais.

| Recurso | Operações |
|---|---|
| Clientes, contas e cartões | `GET` e `POST` em `/clientes`, `/contas` e `/cartoes`. `GET`, `PUT` e `DELETE` nos mesmos caminhos com `/{id}`. |
| Transações | `POST /contas/{id}/depositos`, `/contas/{id}/saques`, `/contas/{id}/transferencias` e `/transacoes/{id}/estornos`. `GET /contas/{id}/extrato`. |
| Faturas | `GET` e `POST /cartoes/{id}/faturas`. `POST /faturas/{id}/fechamento` e `/faturas/{id}/pagamento`. |
| Tarifas | `GET /contas/{id}/tarifas`. |
| Relatórios | `GET /relatorios/clientes-maior-movimentacao`, `/relatorios/contas-saldo-negativo` e `/relatorios/receita-tarifas`. Movimentação e receita recebem `inicio` e `fim` no formato AAAA-MM-DD, com ambas as datas inclusivas. |

- O limite diário de saque e a franquia mensal são compartilhados entre as contas do cliente. A transferência tem o teto por operação especificado para a categoria. A franquia abrange transferências para outros clientes. A tarifa após a franquia é configurável via `BANCO_TARIFA_TRANSFERENCIA` e tem valor inicial de R$ 2,50.
- As tarifas mensais são geradas no mês corrente na primeira manutenção que encontra a conta. Tarifas mensais pendentes são cobradas quando a conta e o cliente estão ativos e há saldo ou crédito disponível. Uma transferência tarifada exige saldo ou crédito para o valor e para a tarifa.
- O estorno exige saldo ou crédito para a reversão e devolve eventual tarifa da transferência. O ranking contabiliza o valor de uma transferência entre contas próprias uma vez e desconsidera operações estornadas.
- A fatura é emitida com valor e vencimento informados. O pagamento é integral, com débito na conta vinculada. Os juros são simples, proporcionais aos dias corridos de atraso sobre uma base de 30 dias, com arredondamento ao centavo. A manutenção usa UTC−03:00 e é executada durante as requisições e a cada minuto com o servidor em execução.
- Excluir uma conta a encerra, e excluir um cartão o cancela. A exclusão física de clientes exige ausência de contas vinculadas. O encerramento exige que todas as faturas estejam quitadas.
- A API não inclui autenticação ou autorização.
