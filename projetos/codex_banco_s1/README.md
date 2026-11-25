# API bancária

API REST em Python 3.10+ com FastAPI e SQLite. O banco é criado na inicialização. Defina `BANCO_DB` para usar outro arquivo. A API é de uso local e não inclui autenticação.

## Execução

```sh
python -m pip install -r requirements.txt
python -m uvicorn app:app
```

A documentação interativa com rotas e esquemas está em `http://127.0.0.1:8000/docs`. O OpenAPI está disponível em `/openapi.json`.

Envie valores monetários com até duas casas decimais. A API armazena centavos inteiros e retorna strings decimais como `"125.50"`. Números de conta e cartão são strings e preservam zeros à esquerda.

## Regras e convenções

- O limite diário de saque e a franquia mensal de transferências externas são compartilhados pelas contas do cliente. Aplica-se o limite por operação às transferências. Transferências internas não consomem a franquia e operações estornadas deixam de ser contabilizadas.
- A tarifa de transferência excedente tem padrão de R$ 5,00 e é configurável por `TARIFA_TRANSFERENCIA_CENTAVOS`. O débito ocorre junto com a transferência e a tarifa é devolvida no estorno.
- A mensalidade é gerada para a competência em curso, uma vez por conta ativa de cliente ativo. A tarifa fica pendente enquanto faltar saldo ou crédito disponível. A manutenção roda a cada minuto e também nas requisições.
- O calendário usa UTC−03:00. Os juros são simples, proporcionais aos dias de atraso sobre um mês de 30 dias e arredondados para centavos. O pagamento integral é debitado da conta vinculada. Após a quitação das faturas em atraso, o cartão pode ser desbloqueado pelo cadastro.
- O estorno respeita o limite de crédito e exige que as contas envolvidas continuem abertas. A exclusão de conta ou cartão encerra a conta ou cancela o cartão, preservando o histórico. O cliente pode ser excluído se não houver contas vinculadas. O encerramento exige saldo zero e quitação das faturas.
- Os relatórios usam datas inclusivas em AAAA-MM-DD nos parâmetros `inicio` e `fim`. O ranking soma depósitos, saques e transferências efetivadas. Uma transferência interna conta uma vez para o titular e uma transferência externa conta para cada titular. A receita usa a categoria registrada na tarifa e os valores cobrados que seguem efetivos.
