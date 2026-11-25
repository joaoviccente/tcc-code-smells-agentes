# API REST para Gestão de Contas Correntes Bancárias

API REST desenvolvida em Python com **FastAPI**, **SQLAlchemy** e **Pydantic v2** para gestão de contas correntes, clientes, cartões de crédito, transações financeiras, faturas, tarifas e relatórios operacionais de um banco.

---

## 🛠️ Requisitos Técnicos e Tecnologias

- **Python 3.12+**
- **FastAPI**: Framework web moderno, assíncrono e de alto desempenho com documentação Swagger/OpenAPI automática.
- **SQLAlchemy 2.0**: ORM para persistência em banco relacional (compatível com SQLite, PostgreSQL, MySQL).
- **Pydantic v2**: Validação estrita de contratos de entrada e saída (CPF, e-mails, enums, limites numéricos e precisão decimal).
- **Pytest + HTTPX**: Suíte completa de testes automatizados com cobertura total das regras de negócio.

---

## 🏛️ Entidades do Sistema

1. **Cliente:**
   - Atributos: `id`, `nome`, `cpf` (único, validado com dígitos verificadores oficiais), `email` (único, validado), `categoria` (`comum`, `premium`, `empresarial`), `situacao` (`ativo`, `bloqueado`), `data_criacao`.
2. **Conta:**
   - Pertence a um cliente.
   - Atributos: `id`, `cliente_id`, `numero` (único), `tipo` (`corrente`, `poupanca`), `saldo`, `limite_de_credito`, `estado` (`ativa`, `bloqueada`, `encerrada`), `data_saldo_negativo_inicio`, `data_criacao`.
3. **Transação:**
   - Atributos: `id`, `conta_id`, `conta_destino_id` (opcional para transferências), `transacao_origem_id` (para estornos), `tipo` (`deposito`, `saque`, `transferencia`, `estorno`), `valor`, `data`, `estado` (`pendente`, `efetivada`, `estornada`), `descricao`.
4. **Cartão:**
   - Pertence a uma conta.
   - Atributos: `id`, `conta_id`, `numero` (único), `limite`, `estado` (`ativo`, `bloqueado`, `cancelado`), `data_criacao`.
5. **Fatura:**
   - Vinculada a um cartão.
   - Atributos: `id`, `cartao_id`, `mes_referencia` (`AAAA-MM`), `valor`, `valor_pago`, `data_vencimento`, `estado` (`aberta`, `fechada`, `paga`, `atrasada`), `juros_acumulados`, `data_pagamento`.
6. **Tarifa:**
   - Vinculada a uma conta.
   - Atributos: `id`, `conta_id`, `tipo` (ex: `mensalidade`, `transferencia_excedente`), `valor`, `data`, `estado` (`pendente`, `cobrada`, `isenta`).

---

## 📊 Regras por Categoria de Cliente

| Categoria | Limite Diário de Saque | Limite por Transferência | Tarifa Mensal | Transações Isentas / Mês | Juros de Atraso de Fatura |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Comum** | R$ 1.000,00 | R$ 5.000,00 | R$ 30,00 | 3 transações | 8% ao mês |
| **Premium** | R$ 5.000,00 | R$ 50.000,00 | R$ 0,00 (sem tarifa) | Ilimitadas | 5% ao mês |
| **Empresarial** | R$ 20.000,00 | R$ 200.000,00 | R$ 120,00 | 50 transações | 3% ao mês |

---

## ⚖️ Regras de Negócio Implementadas

1. **Permissão de Saque e Transferência:**
   - Permitidos estritamente em contas com estado `ativa` e cujo titular possua situação `ativo`.
   - O saque respeita o limite diário acumulado no dia da categoria do cliente (`HTTP 400` caso excedido).
   - A transferência respeita o teto por operação definido para a categoria (`HTTP 400` caso excedido).
2. **Limite de Crédito:**
   - O saldo da conta pode ficar negativo até o valor do `limite_de_credito` contratado.
   - Tentativas de debitar valor além de `saldo + limite_de_credito` são rejeitadas com `HTTP 400`.
3. **Isenção e Tarifação de Transferências:**
   - Transferências entre contas do **mesmo cliente** são 100% isentas de tarifa (registradas como `isenta`).
   - Transferências para contas de outros clientes consomem a franquia mensal de transações isentas da categoria.
   - Após esgotada a franquia, é debitada automaticamente a tarifa avulsa da conta e registrada com estado `cobrada`.
4. **Estorno de Transações:**
   - Qualquer transação efetivada (depósito, saque ou transferência) pode ser estornada em até 24 horas (`HTTP 400` caso o prazo expire).
   - O estorno reverte os saldos das contas envolvidas, altera o estado da transação original para `estornada` e cria uma nova transação do tipo `estorno` com estado `efetivada`.
5. **Atraso de Faturas e Bloqueio de Cartão:**
   - Faturas não quitadas até o vencimento passam automaticamente ao estado `atrasada`.
   - Acumulam juros proporcionais conforme a categoria do cliente (8%, 5% ou 3% ao mês).
   - Caso o atraso ultrapasse **10 dias**, o cartão vinculado é automaticamente alterado para o estado `bloqueado`.
6. **Saldo Negativo Prolongado:**
   - Contas que permaneçam com saldo negativo por mais de **30 dias** bloqueiam o cliente (`situacao = bloqueado`) e todos os cartões vinculados a todas as contas desse cliente (`estado = bloqueado`).
7. **Encerramento de Conta:**
   - Exige que o saldo da conta seja exatamente zero (`R$ 0,00`) e que não exista nenhuma fatura pendente ou aberta nos cartões vinculados.
   - Ao encerrar a conta (`estado = encerrada`), todos os seus cartões passam para `estado = cancelado`.

---

## 📡 Endpoints da API

### Clientes
- `POST /clientes` - Cria cliente (valida CPF e e-mail únicos) `[201]`
- `GET /clientes` - Lista clientes (filtros por `categoria`, `situacao`) `[200]`
- `GET /clientes/{id}` - Detalhes do cliente `[200 / 404]`
- `PUT /clientes/{id}` - Atualiza dados cadastrais `[200 / 404 / 409]`
- `DELETE /clientes/{id}` - Exclui cliente se não houver contas ativas `[204 / 400]`

### Contas
- `POST /contas` - Cria conta corrente ou poupança `[201 / 400 / 404 / 409]`
- `GET /contas` - Lista contas (filtros por `cliente_id`, `estado`) `[200]`
- `GET /contas/{id}` - Detalhes da conta `[200 / 404]`
- `PUT /contas/{id}` - Atualiza limite de crédito ou tipo `[200 / 400]`
- `DELETE /contas/{id}` e `POST /contas/{id}/encerrar` - Encerra a conta aplicando a Regra 7 `[200 / 400]`

### Cartões
- `POST /cartoes` - Emite cartão para conta ativa `[201 / 400 / 404 / 409]`
- `GET /cartoes` - Lista cartões (filtros por `conta_id`, `estado`) `[200]`
- `GET /cartoes/{id}` - Detalhes do cartão `[200 / 404]`
- `PUT /cartoes/{id}` - Atualiza limite ou estado `[200 / 400]`
- `DELETE /cartoes/{id}` - Cancela cartão `[200 / 404]`

### Transações
- `POST /transacoes/deposito` - Realiza depósito `[201 / 400 / 404]`
- `POST /transacoes/saque` - Realiza saque (Regras 1 e 2) `[201 / 400 / 404]`
- `POST /transacoes/transferencia` - Realiza transferência (Regras 1, 2 e 3) `[201 / 400 / 404]`
- `POST /transacoes/{id}/estorno` - Estorno em até 24h (Regra 4) `[200 / 400 / 404]`
- `GET /contas/{id}/extrato` - Extrato detalhado com filtros por data `[200 / 404]`

### Faturas
- `GET /cartoes/{id}/faturas` - Lista faturas de um cartão com atualização de juros `[200 / 404]`
- `POST /cartoes/{id}/faturas` e `POST /faturas` - Gera fatura para cartão `[201 / 400 / 404]`
- `GET /faturas/{id}` - Detalhes da fatura `[200 / 404]`
- `POST /faturas/{id}/pagamento` - Registra pagamento integral ou parcial `[200 / 400 / 404]`

### Tarifas
- `GET /contas/{id}/tarifas` - Lista tarifas vinculadas à conta `[200 / 404]`
- `POST /tarifas/cobrar-mensalidades` - Executa cobrança de mensalidades das contas `[200]`

### Relatórios
- `GET /relatorios/clientes-maior-movimentacao` - Clientes ordenados por maior volume movimentado no período `[200]`
- `GET /relatorios/contas-saldo-negativo` - Contas com saldo negativo e dias em atraso `[200]`
- `GET /relatorios/receita-tarifas-por-categoria` - Total arrecadado com tarifas discriminado por categoria de cliente `[200]`

### Rotinas Automáticas
- `POST /rotinas/processar-faturas-atrasadas` - Atualiza juros e bloqueia cartões após 10 dias de atraso (Regra 5) `[200]`
- `POST /rotinas/processar-contas-negativas` - Bloqueia cliente e cartões caso a conta fique negativa por > 30 dias (Regra 6) `[200]`

---

## 🚀 Como Executar o Projeto

### 1. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 2. Iniciar o Servidor
```bash
uvicorn app.main:app --reload --port 8000
```

### 3. Acessar a Documentação Interativa
- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🧪 Como Executar a Suíte de Testes

Os testes cobrem exaustivamente todas as entidades, endpoints, códigos de status HTTP e todas as 7 regras de negócio:

```bash
pytest -v
```
