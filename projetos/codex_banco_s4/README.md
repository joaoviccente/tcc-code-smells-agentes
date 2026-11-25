# API bancária

Requer Python 3.11 ou superior. O SQLite cria o arquivo de banco na primeira execução.

```sh
python -m pip install -r requirements.txt
python -m uvicorn main:app
```

A documentação interativa fica em http://127.0.0.1:8000/docs. Use a variável de ambiente `BANCO_DB` para escolher o arquivo SQLite. Envie valores monetários em reais, preferencialmente como strings decimais, por exemplo `"123.45"`. As respostas usam duas casas decimais.

## Rotas

| Método | Caminho | Operação |
| --- | --- | --- |
| GET, POST | `/clientes`, `/contas`, `/cartoes` | Listar e criar |
| GET, PUT, DELETE | `/clientes/{id}`, `/contas/{id}`, `/cartoes/{id}` | Consultar, editar e excluir, encerrar ou cancelar |
| POST | `/contas/{id}/depositos`, `/contas/{id}/saques` | Enviar `valor` |
| POST | `/contas/{id}/transferencias` | Enviar `valor` e `destino_id` |
| POST | `/transacoes/{id}/estorno` | Estornar a transação |
| GET | `/contas/{id}/extrato`, `/contas/{id}/tarifas` | Consultar movimentações e tarifas |
| GET, POST | `/cartoes/{id}/faturas` | Listar e emitir faturas |
| POST | `/faturas/{id}/pagamento` | Registrar a quitação |
| GET | `/relatorios/movimentacao` | Ranking com `inicio` e `fim` inclusivos |
| GET | `/relatorios/saldos-negativos` | Contas com saldo negativo |
| GET | `/relatorios/receita-tarifas` | Receita por categoria, com `inicio` e `fim` opcionais |

As datas são informadas em `AAAA-MM-DD`. A referência da fatura usa `AAAA-MM`. A API responde com 201 para criação, 204 para exclusão, 404 para registro inexistente, 409 para conflito de estado ou regra de negócio e 422 para entrada inválida.

## Convenções adotadas

- O limite de saque é acumulado por cliente e dia no horário bancário UTC−03. O limite de transferência vale por operação. A franquia mensal é compartilhada pelas contas do cliente e é usada apenas em transferências para outros titulares.
- A mensalidade é lançada por conta e competência, desde o mês de abertura. A tarifa por transferência excedente é de **R$ 1,00** por padrão e pode ser configurada com `BANCO_TARIFA_EXCEDENTE`. As tarifas aguardam saldo ou crédito disponível para cobrança. O estorno libera a franquia usada e devolve a tarifa da transferência quando ela já foi cobrada.
- Os juros são simples, proporcionais aos dias de atraso em um mês de 30 dias. O cartão é bloqueado a partir do 11º dia de atraso. O pagamento registra a quitação integral, incluindo os juros apurados, sem movimentar a conta.
- O encerramento exige saldo zero e quitação de todas as faturas. O encerramento e o cancelamento preservam o histórico. Clientes vinculados a contas recebem 409 na exclusão.
- As rotinas de calendário executam na inicialização, durante as consultas e operações e a cada 60 segundos enquanto o serviço está ativo.

## Testes

```sh
python -m pip install pytest httpx
python -m pytest -q
```
