# API REST para Gestão de Contas Correntes Bancárias

API REST desenvolvida em Python (FastAPI + SQLAlchemy + Pydantic + SQLite/PostgreSQL) para a gestão completa de clientes, contas bancárias, cartões, faturas, tarifas, transações financeiras e relatórios analíticos, seguindo estritamente as regras de negócio e limites por categoria de cliente.

---

## 🏛️ Entidades do Sistema

1. **Cliente**
   - Atributos: `nome`, `cpf` (único, validado por dígito verificador), `email` (único, validado), `categoria` (`comum`, `premium`, `empresarial`), `situacao` (`ativo`, `bloqueado`).
2. **Conta**
   - Atributos: pertence a um cliente (`cliente_id`), `numero` (único), `tipo` (`corrente`, `poupanca`), `saldo`, `limite_credito`, `estado` (`ativa`, `bloqueada`, `encerrada`), `saldo_negativo_desde`.
3. **Transação**
   - Atributos: `conta_id`, `conta_destino_id` (para transferências), `transacao_origem_id` (para estorno), `tipo` (`deposito`, `saque`, `transferencia`, `estorno`), `valor`, `data`, `estado` (`pendente`, `efetivada`, `estornada`), `descricao`.
4. **Cartão**
   - Atributos: pertence a uma conta (`conta_id`), `numero` (único), `limite`, `estado` (`ativo`, `bloqueado`, `cancelado`).
5. **Fatura**
   - Atributos: pertence a um cartão (`cartao_id`), `mes_referencia` (ex: `2026-11`), `valor`, `data_vencimento`, `estado` (`aberta`, `fechada`, `paga`, `atrasada`), `valor_pago`, `data_pagamento`, `juros_acumulados`.
6. **Tarifa**
   - Atributos: pertence a uma conta (`conta_id`), `tipo` (`mensalidade`, `transferencia`, `saque`, `outro`), `valor`, `estado` (`pendente`, `cobrada`, `isenta`), `data`.

---

## 📊 Regras por Categoria de Cliente

| Parâmetro | Comum | Premium | Empresarial |
| :--- | :--- | :--- | :--- |
| **Limite diário de saque** | R$ 1.000,00 | R$ 5.000,00 | R$ 20.000,00 |
| **Limite por transferência** | R$ 5.000,00 | R$ 50.000,00 | R$ 200.000,00 |
| **Tarifa mensal** | R$ 30,00 | Isenta (R$ 0,00) | R$ 120,00 |
| **Transações isentas por mês** | 3 | Ilimitadas | 50 |
| **Juros de atraso de fatura** | 8% ao mês | 5% ao mês | 3% ao mês |

---

## ⚙️ Regras de Negócio Implementadas

1. **Permissão de Saque e Transferência**:
   - Só são permitidos em conta no estado `ativa` e cliente no estado `ativo`.
   - Saque valida o total já sacado no dia civil corrente somado ao valor solicitado, respeitando o limite diário da categoria.
   - Transferência respeita o teto máximo permitido por operação de acordo com a categoria do cliente remetente.
2. **Limite de Saldo Negativo (Cheque Especial)**:
   - O saldo pode ficar negativo até o limite de crédito (`saldo + limite_credito >= valor_debito`). Abaixo disso, a operação é rejeitada com código HTTP 400.
   - O sistema registra o momento exato em que o saldo passa a ficar negativo (`saldo_negativo_desde`). Ao retornar a `>= 0`, o marcador é limpo.
3. **Isenção e Cobrança de Tarifas em Transferências**:
   - Transferência entre contas do mesmo cliente é sempre **isenta** de tarifa (`estado = isenta`).
   - Transferências para terceiros consomem a franquia mensal de transações isentas da categoria (Comum: 3, Premium: ilimitadas, Empresarial: 50).
   - Esgotada a franquia no mês corrente, é tarifada no valor padrão de R$ 10,00 debitado do saldo (`estado = cobrada`).
4. **Estorno de Transações**:
   - Uma transação efetivada pode ser estornada em até **24 horas**.
   - O estorno reverte os saldos das contas envolvidas (verificando disponibilidade de fundos/limite no destino/origem).
   - A transação original passa ao estado `estornada` e uma nova transação do tipo `estorno` com estado `efetivada` é registrada.
5. **Atraso de Fatura e Bloqueio de Cartão**:
   - Faturas não quitadas após a data de vencimento passam para o estado `atrasada` e acumulam juros pro-rata com base na taxa mensal da categoria.
   - Ao ultrapassar **10 dias de atraso**, o cartão vinculado é automaticamente `bloqueado`.
   - Ao efetuar o pagamento da fatura (`POST /faturas/{id}/pagamento`), o cartão é desbloqueado se não houver outras pendências > 10 dias.
6. **Inadimplência Prolongada (> 30 dias)**:
   - Se uma conta permanecer com saldo negativo por mais de **30 dias**, o cliente titular tem sua situação alterada para `bloqueado` e todos os seus cartões passam para `bloqueado`.
7. **Encerramento de Conta**:
   - O encerramento exige **saldo exatamente igual a zero** e **nenhuma fatura aberta ou em atraso** nos cartões vinculados.
   - Ao encerrar a conta (`POST /contas/{id}/encerrar`), a conta passa para `encerrada` e todos os cartões da conta são `cancelados`.

---

## 🚀 Endpoints da API

### Clientes
- `POST /clientes` - Cadastra um novo cliente (Valida CPF e e-mail único)
- `GET /clientes` - Lista clientes cadastrados
- `GET /clientes/{id}` - Obtém dados de um cliente
- `PUT /clientes/{id}` - Atualiza dados cadastrais
- `DELETE /clientes/{id}` - Remove cliente

### Contas
- `POST /contas` - Cria uma conta bancária (corrente ou poupança)
- `GET /contas` - Lista contas (suporta filtro por `cliente_id`)
- `GET /contas/{id}` - Obtém dados de uma conta
- `PUT /contas/{id}` - Atualiza tipo, limite ou estado
- `POST /contas/{id}/encerrar` - Encerra a conta aplicando a Regra 7
- `DELETE /contas/{id}` - Exclui conta zerada
- `GET /contas/{id}/extrato` - Extrato detalhado com filtros de data

### Cartões
- `POST /cartoes` - Emite cartão para conta ativa
- `GET /cartoes` - Lista cartões (suporta filtro por `conta_id`)
- `GET /cartoes/{id}` - Detalhes do cartão
- `PUT /cartoes/{id}` - Atualiza limite ou estado
- `DELETE /cartoes/{id}` - Remove cartão

### Transações
- `POST /transacoes/deposito` - Realiza depósito em conta
- `POST /transacoes/saque` - Realiza saque (aplica limite diário e saldo + limite)
- `POST /transacoes/transferencia` - Realiza transferência (aplica franquia e tarifas)
- `POST /transacoes/{id}/estorno` - Estorno dentro da janela de 24 horas
- `GET /transacoes` - Lista histórico de transações
- `GET /transacoes/{id}` - Detalhes de uma transação

### Faturas
- `POST /cartoes/{id}/faturas` - Lança nova fatura para o cartão
- `GET /cartoes/{id}/faturas` - Lista faturas de um cartão
- `GET /faturas/{id}` - Consulta fatura com cálculo dinâmico de juros
- `POST /faturas/{id}/pagamento` - Registra pagamento da fatura (opção de debitar da conta)

### Tarifas
- `GET /contas/{id}/tarifas` - Lista tarifas registradas na conta
- `POST /contas/{id}/tarifas/cobrar-mensalidade` - Processa cobrança de mensalidade da categoria
- `POST /tarifas` - Registra tarifa avulsa

### Relatórios
- `GET /relatorios/clientes-maior-movimentacao` - Ranking de clientes por volume movimentado em determinado período
- `GET /relatorios/contas-saldo-negativo` - Contas com saldo negativo e contagem de dias em débito
- `GET /relatorios/receita-tarifas-categoria` - Receita arrecadada com tarifas agrupada por categoria (`comum`, `premium`, `empresarial`)

### Rotinas de Negócio
- `POST /rotinas/processar-faturas-atrasadas` - Atualiza juros e bloqueia cartões em atraso > 10 dias
- `POST /rotinas/processar-saldo-negativo` - Bloqueia clientes e cartões com saldo negativo > 30 dias

---

## 🛠️ Tecnologias e Requisitos Técnicos

- **Linguagem**: Python 3.12+
- **Framework Web**: FastAPI
- **Validação de Dados**: Pydantic v2
- **ORM / Banco de Dados**: SQLAlchemy 2.0 (compatível com SQLite e PostgreSQL)
- **Servidor ASGI**: Uvicorn
- **Testes**: Pytest

---

## 🏃 Como Executar

1. **Instalar dependências**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Iniciar o servidor**:
   ```bash
   python run.py
   ```
   Ou via uvicorn:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

3. **Documentação interativa Swagger UI**:
   Acesse no navegador: [http://localhost:8000/docs](http://localhost:8000/docs)

4. **Executar a suíte de testes automatizados**:
   ```bash
   pytest -v
   ```
