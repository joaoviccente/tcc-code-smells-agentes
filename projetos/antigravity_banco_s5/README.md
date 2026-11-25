# API REST para Gestão de Contas Correntes Bancárias

API REST desenvolvida em Python com **FastAPI** e **SQLAlchemy**, destinada ao gerenciamento completo de contas correntes e poupança, clientes, cartões, transações financeiras, faturas, tarifas e relatórios analíticos, seguindo rigorosamente as regras de negócio e limites por categoria de cliente.

---

## 🛠️ Tecnologias e Requisitos Técnicos

- **Linguagem**: Python 3.12+
- **Framework Web**: [FastAPI](https://fastapi.tiangolo.com/) (validação automática com Pydantic v2 e documentação interativa Swagger/OpenAPI)
- **Persistência**: [SQLAlchemy 2.0](https://www.sqlalchemy.org/) com suporte relacional (SQLite por padrão, facilmente configurável para PostgreSQL/MySQL)
- **Validação de Entrada**: Validação de CPF oficial brasileiro (dígitos verificadores via algoritmo módulo 11), e-mails válidos, limites e valores positivos.
- **Códigos HTTP**: Respeito às convenções REST:
  - `200 OK`: Operações de leitura, atualização e execução de regras bem-sucedidas.
  - `201 Created`: Criação bem-sucedida de registros (clientes, contas, cartões, transações, faturas).
  - `204 No Content`: Exclusão concluída.
  - `400 Bad Request`: Violação de regras de negócio (saldo insuficiente, limites de saque/transferência excedidos, estorno após 24h, encerramento de conta com saldo ou faturas pendentes).
  - `404 Not Found`: Recurso não localizado.
  - `409 Conflict`: Conflito de unicidade (CPF duplicado, e-mail duplicado, número de conta/cartão duplicado).
  - `422 Unprocessable Entity`: Erros de validação estrutural de schemas (CPF inválido, tipo numérico incorreto).

---

## 📋 Entidades do Sistema

1. **Cliente**:
   - `id`: Identificador único
   - `nome`: Nome completo
   - `cpf`: CPF único (com validação completa de formato e dígitos verificadores)
   - `email`: E-mail único e validado
   - `categoria`: `comum`, `premium` ou `empresarial`
   - `situacao`: `ativo` ou `bloqueado`
2. **Conta**:
   - `id`: Identificador único
   - `cliente_id`: Chave estrangeira referenciando o titular
   - `numero`: Número único da conta
   - `tipo`: `corrente` ou `poupanca`
   - `saldo`: Saldo atual (precisão Decimal)
   - `limite_credito`: Limite de cheque especial / crédito contratado
   - `estado`: `ativa`, `bloqueada` ou `encerrada`
   - `data_saldo_negativo_inicio`: Registro de quando o saldo ficou negativo
3. **Transação**:
   - `id`: Identificador único
   - `conta_id`: Conta de origem/principal
   - `conta_destino_id`: Conta de destino (opcional, aplicável em transferências)
   - `tipo`: `deposito`, `saque`, `transferencia` ou `estorno`
   - `valor`: Valor da operação (positivo)
   - `data`: Data e hora da transação (UTC)
   - `estado`: `pendente`, `efetivada` ou `estornada`
   - `transacao_origem_id`: Vínculo para estornos
4. **Cartão**:
   - `id`: Identificador único
   - `conta_id`: Conta associada
   - `numero`: Número do cartão (único)
   - `limite`: Limite de crédito do cartão
   - `estado`: `ativo`, `bloqueado` ou `cancelado`
5. **Fatura**:
   - `id`: Identificador único
   - `cartao_id`: Cartão associado
   - `mes_referencia`: Mês de competência (formato `AAAA-MM`)
   - `valor`: Valor original da fatura
   - `data_vencimento`: Data de vencimento
   - `data_pagamento`: Data/hora do pagamento
   - `valor_pago`: Valor efetivamente pago
   - `juros_acumulados`: Juros calculados por atraso
   - `estado`: `aberta`, `fechada`, `paga` ou `atrasada`
6. **Tarifa**:
   - `id`: Identificador único
   - `conta_id`: Conta tarifada
   - `tipo`: `mensalidade` ou `transferencia_excedente`
   - `valor`: Valor da tarifa
   - `estado`: `pendente`, `cobrada` ou `isenta`
   - `data`: Data/hora do registro

---

## 🎯 Regras por Categoria de Cliente

| Parâmetro | Comum | Premium | Empresarial |
| :--- | :--- | :--- | :--- |
| **Limite diário de saque** | R$ 1.000,00 | R$ 5.000,00 | R$ 20.000,00 |
| **Limite por transferência** | R$ 5.000,00 | R$ 50.000,00 | R$ 200.000,00 |
| **Tarifa mensal** | R$ 30,00 | R$ 0,00 (Sem tarifa) | R$ 120,00 |
| **Transações isentas por mês** | 3 | Ilimitadas | 50 |
| **Juros de atraso de fatura** | 8% ao mês | 5% ao mês | 3% ao mês |

---

## ⚖️ Regras de Negócio Implementadas

1. **Permissão de Saque e Transferência**: Só são permitidos em conta `ativa` de cliente `ativo`, respeitando os limites diários acumulados de saque e limites por transferência da categoria.
2. **Limite de Crédito**: O saldo pode ficar negativo até o limite de crédito (`saldo + limite_credito >= valor`). Caso contrário, a operação é rejeitada com código 400.
3. **Franquia de Transferências**:
   - Transferências entre contas do **mesmo cliente** são sempre **isentas** de tarifa.
   - Transferências entre clientes diferentes consomem a franquia mensal da categoria (Comum: 3, Premium: ilimitadas, Empresarial: 50). Esgotada a franquia, gera tarifa de transferência excedente (R$ 10,00) debitada da conta.
4. **Estorno de Transações**:
   - Qualquer transação efetivada pode ser estornada em **até 24 horas**.
   - Reverte os saldos das contas envolvidas.
   - Atualiza a transação original para `estornada` e registra uma nova transação do tipo `estorno`.
5. **Atraso de Fatura e Bloqueio de Cartão**:
   - Faturas não pagas até o vencimento passam ao estado `atrasada` e acumulam juros pro-rata com base na taxa mensal da categoria.
   - Após **10 dias de atraso**, o cartão é bloqueado automaticamente. Ao pagar, se não houver outras faturas em atraso crítico, o cartão é desbloqueado.
6. **Inadimplência por Saldo Negativo**:
   - Conta com saldo negativo por **mais de 30 dias** bloqueia o cliente e todos os seus cartões em todas as suas contas.
7. **Encerramento de Conta**:
   - Exige **saldo exatamente zero** e **nenhuma fatura aberta ou atrasada**.
   - Ao encerrar, todos os cartões vinculados à conta são cancelados e a conta passa para o estado `encerrada`.

---

## 🚀 Instalação e Execução

### 1. Clonar e Acessar o Diretório
```bash
cd C:\tcc\coleta\antigravity_banco_s5
```

### 2. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 3. Executar o Servidor de Desenvolvimento
```bash
python -m uvicorn app.main:app --reload --port 8000
```
- **Documentação Swagger Interativa**: `http://127.0.0.1:8000/docs`
- **Documentação Redoc**: `http://127.0.0.1:8000/redoc`

### 4. Executar os Testes Automatizados
```bash
python -m pytest -v
```

---

## 📡 Endpoints da API

### Clientes
- `POST /clientes`: Cadastra cliente (`nome`, `cpf`, `email`, `categoria`, `situacao`).
- `GET /clientes`: Lista clientes com filtros (`categoria`, `situacao`, `skip`, `limit`).
- `GET /clientes/{id}`: Detalhes do cliente.
- `PUT /clientes/{id}`: Atualiza dados cadastrais.
- `DELETE /clientes/{id}`: Remove cliente sem contas ativas.

### Contas
- `POST /contas`: Cria conta (`cliente_id`, `numero`, `tipo`, `limite_credito`).
- `GET /contas`: Lista contas com filtros (`cliente_id`, `tipo`, `estado`).
- `GET /contas/{id}`: Detalhes da conta.
- `PUT /contas/{id}`: Atualiza limite de crédito ou tipo.
- `POST /contas/{id}/encerrar`: Encerra a conta (valida saldo zero e faturas).
- `GET /contas/{id}/extrato`: Extrato completo com saldo disponível.
- `GET /contas/{id}/tarifas`: Lista tarifas da conta.
- `POST /contas/{id}/cobrar-mensalidade`: Aplica e debita a tarifa mensal da categoria.

### Cartões
- `POST /cartoes`: Emite cartão (`conta_id`, `numero`, `limite`).
- `GET /cartoes`: Lista cartões da conta ou do sistema.
- `GET /cartoes/{id}`: Detalhes do cartão.
- `PUT /cartoes/{id}`: Altera limite ou estado.
- `DELETE /cartoes/{id}`: Cancela cartão.
- `GET /cartoes/{id}/faturas`: Lista faturas vinculadas ao cartão.

### Transações
- `POST /transacoes/deposito`: Depósito em conta.
- `POST /transacoes/saque`: Saque respeitando limite diário e saldo + limite.
- `POST /transacoes/transferencia`: Transferência com franquia e tarifação.
- `POST /transacoes/{id}/estorno`: Estorno em até 24 horas.
- `GET /transacoes/{id}`: Consulta transação.

### Faturas
- `POST /faturas`: Criação de fatura.
- `GET /faturas/{id}`: Detalhes com juros atualizados em caso de atraso.
- `POST /faturas/{id}/pagamento`: Pagamento da fatura (com opção de débito em conta).

### Tarifas
- `GET /tarifas`: Listagem geral de tarifas.
- `GET /tarifas/conta/{conta_id}`: Tarifas de uma conta específica.

### Relatórios
- `GET /relatorios/clientes-maior-movimentacao?data_inicio=...&data_fim=...&limite=10`: Clientes com maior volume financeiro transacionado no período.
- `GET /relatorios/contas-saldo-negativo`: Contas com saldo negativo e tempo em dias.
- `GET /relatorios/receita-tarifas-categoria`: Receita consolidada de tarifas agrupada por categoria (`comum`, `premium`, `empresarial`).

### Rotinas Automáticas
- `POST /rotinas/verificar-inadimplencia`: Processa faturas vencidas e bloqueio de clientes/cartões por saldo negativo superior a 30 dias.
