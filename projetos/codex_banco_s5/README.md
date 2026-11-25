# API bancária

Requer Python 3.12. Execute na raiz do projeto.

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app
```

A documentação interativa está em http://localhost:8000/docs. O SQLite cria `banco.sqlite3` automaticamente. Defina `BANCO_DB` para usar outro caminho. As operações gravam valores em centavos inteiros e retornam quantias em reais como strings com duas casas decimais. Contas começam com saldo zero.

| Métodos | Rota |
| --- | --- |
| POST, GET | /clientes, /contas, /cartoes |
| GET, PUT, DELETE | /clientes/{id}, /contas/{id}, /cartoes/{id} |
| POST | /transacoes/deposito, /transacoes/saque, /transacoes/transferencia |
| POST | /transacoes/{id}/estorno |
| GET | /contas/{id}/extrato, /contas/{id}/tarifas |
| POST, GET | /cartoes/{id}/faturas |
| POST | /faturas/{id}/fechamento, /faturas/{id}/pagamento |
| GET | /relatorios/clientes-maior-movimentacao?inicio=AAAA-MM-DD&fim=AAAA-MM-DD |
| GET | /relatorios/contas-saldo-negativo |
| GET | /relatorios/receita-tarifas (aceita inicio e fim opcionais) |

O depósito e o saque recebem `conta_id` e `valor`. A transferência recebe `origem_id`, `destino_id` e `valor`. A emissão de fatura recebe `mes_referencia` no formato AAAA-MM, `vencimento` em AAAA-MM-DD, `valor` e opcionalmente `estado`. O pagamento integral debita a conta vinculada ao cartão.

## Critérios adotados

- Os limites diários são acumulados por titular, separadamente para saques e transferências, no fuso UTC−03:00. O teto por transferência também vale como teto acumulado diário de transferências, pois o enunciado não fornece outro valor. Estornos não restauram limites nem franquias já usados.
- A franquia mensal é por titular e se aplica a transferências para outros clientes. A tarifa excedente tem valor padrão de R$ 5,00, configurável por `BANCO_TARIFA_TRANSFERENCIA_CENTAVOS`. A mensalidade é lançada uma vez por conta no primeiro processamento do mês em que a conta é encontrada. A cobrança fica pendente quando o saldo e o crédito disponíveis são insuficientes ou quando a conta ou o cliente estão bloqueados.
- O atraso começa no dia seguinte ao vencimento. Juros simples incidem sobre o valor original, à razão de 1/30 da taxa mensal por dia, com arredondamento em centavos. A API processa prazos no início da aplicação, antes das operações e a cada minuto durante a execução.
- O encerramento exige saldo zero e todas as faturas quitadas. O DELETE de conta encerra a conta e o DELETE de cartão cancela o cartão, preservando o histórico. Clientes vinculados a contas não podem ser excluídos.
- A movimentação soma os valores efetivados do período, exclui estornos e operações estornadas, e conta uma transferência interna uma vez. Transferências entre clientes contam para ambos. A receita considera somente tarifas efetivamente cobradas.
