# API de Gestão de Contas Correntes Bancárias

API REST desenvolvida em Python com **FastAPI** e **SQLAlchemy** para gestão bancária completa, contemplando clientes, contas correntes/poupança, cartões, faturas, tarifas, transações financeiras e relatórios operacionais.

---

## 🏛️ Entidades e Modelos de Dados

- **Cliente**:
  - `id`: Identificador único.
  - `nome`: Nome completo do cliente.
  - `cpf`: Cadastro de Pessoa Física com validação oficial de dígitos verificadores e unicidade.
  - `email`: Endereço de e-mail válido e único.
  - `categoria`: `comum`, `premium` ou `empresarial`.
  - `situacao`: `ativo` ou `bloqueado`.

- **Conta**:
  - Pertence a um cliente (`cliente_id`).
  - `numero`: Número único da conta.
  - `tipo`: `corrente` ou `poupanca`.
  - `saldo`: Saldo em `Decimal(14, 2)`.
  - `limite_credito`: Limite de cheque especial / crédito contratado.
  - `estado`: `ativa`, `bloqueada` ou `encerrada`.
  - `data_saldo_negativo_desde`: Rastreamento temporal para inadimplência (> 30 dias).

- **Transação**:
  - `conta_id`: Conta de origem/titular.
  - `conta_destino_id`: Conta de destino (em caso de transferências).
  - `tipo`: `deposito`, `saque`, `transferencia`, `estorno`.
  - `valor`: Valor monetário da operação.
  - `data`: Carimbo de data/hora UTC da operação.
  - `estado`: `pendente`, `efetivada`, `estornada`.
  - `transacao_origem_id`: Vínculo para estornos.

- **Cartão**:
  - Pertence a uma conta (`conta_id`).
  - `numero`: Número único do cartão.
  - `limite`: Limite de crédito do cartão.
  - `estado`: `ativo`, `bloqueado`, `cancelado`.

- **Fatura**:
  - Pertence a um cartão (`cartao_id`).
  - `mes_referencia`: Formato `AAAA-MM` (ex: `2026-11`).
  - `valor`: Valor atualizado (inclui juros se em atraso).
  - `valor_original`: Valor base da fatura.
  - `data_vencimento`: Data de vencimento.
  - `data_pagamento`: Data/hora em que a fatura foi quitada.
  - `estado`: `aberta`, `fechada`, `paga`, `atrasada`.
  - `dias_atraso`: Dias decorridos após vencimento.
  - `juros_acumulados`: Juros calculados de acordo com a categoria.

- **Tarifa**:
  - Pertence a uma conta (`conta_id`).
  - `tipo`: Tipo da tarifa (ex: `manutencao_mensal`, `transferencia_excedente`).
  - `valor`: Valor da tarifa debitada.
  - `data`: Data/hora do lançamento.
  - `estado`: `pendente`, `cobrada`, `isenta`.

---

## 📊 Regras por Categoria de Cliente

| Parâmetro | Comum | Premium | Empresarial |
| :--- | :--- | :--- | :--- |
| **Limite diário de saque** | R$ 1.000,00 | R$ 5.000,00 | R$ 20.000,00 |
| **Limite por transferência** | R$ 5.000,00 | R$ 50.000,00 | R$ 200.000,00 |
| **Tarifa mensal** | R$ 30,00 | R$ 0,00 (Sem tarifa) | R$ 120,00 |
| **Transações isentas / mês** | 3 | Ilimitadas | 50 |
| **Juros de atraso de fatura** | 8% ao mês | 5% ao mês | 3% ao mês |

---

## ⚙️ Regras de Negócio Implementadas

1. **Validação de Saque e Transferência**:
   - Só são permitidos se a conta estiver `ativa` e o cliente titular estiver `ativo`.
   - Saque valida o limite diário acumulado no dia da data da transação conforme a categoria.
   - Transferência valida o limite máximo permitido por operação para a categoria.
2. **Limite de Crédito**:
   - O saldo da conta pode ficar negativo até o limite de crédito contratado (`saldo >= -limite_credito`). Abaixo desse valor, a operação é negada com código HTTP 400.
3. **Franquia de Transferência e Tarifas**:
   - Transferência entre contas do **mesmo cliente** é sempre isenta de tarifas.
   - Transferências para contas de outros clientes consomem a franquia mensal de transações isentas (Comum: 3, Empresarial: 50, Premium: ilimitada).
   - Esgotada a franquia, é gerada e debitada uma tarifa de transferência excedente (R$ 10,00).
4. **Estorno de Transações**:
   - Qualquer transação efetivada pode ser estornada em até **24 horas**.
   - O estorno reverte os saldos das contas envolvidas e cria uma nova transação do tipo `estorno` vinculada à original.
   - Estornos não podem ser estornados e transações após 24h são recusadas.
5. **Atraso de Fatura e Bloqueio de Cartão**:
   - Faturas não quitadas até o vencimento passam automaticamente ao estado `atrasada`.
   - Acumulam juros proporcionais aos dias de atraso conforme a taxa da categoria.
   - Ao ultrapassar **10 dias de atraso**, o cartão vinculado é automaticamente bloqueado (`cartao.estado = 'bloqueado'`).
6. **Saldo Negativo Prolongado**:
   - Conta que permaneça com saldo negativo por mais de **30 dias** bloqueia o cliente (`situacao = 'bloqueado'`) e todos os cartões de todas as contas vinculadas a ele.
7. **Encerramento de Conta**:
   - Exige que o saldo seja exatamente `R$ 0,00`.
   - Exige que não haja nenhuma fatura `aberta` ou `atrasada` nos cartões vinculados à conta.
   - Ao encerrar, todos os cartões da conta passam ao estado `cancelado`.

---

## 🚀 Como Executar o Projeto

### Pré-requisitos
- Python 3.10+ (testado em Python 3.12)
- Pip

### 1. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 2. Iniciar a API
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- Documentação Interativa Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- Documentação ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 3. Executar a Suíte de Testes
```bash
python -m pytest -v
```

---

## 📡 Visão Geral dos Endpoints

### Clientes
- `POST /clientes` - Cadastrar novo cliente (valida CPF e e-mail únicos).
- `GET /clientes` - Listar clientes (filtros: `categoria`, `situacao`).
- `GET /clientes/{id}` - Obter detalhes do cliente por ID.
- `PUT /clientes/{id}` - Atualizar dados do cliente.
- `DELETE /clientes/{id}` - Remover cliente (valida contas com saldo).

### Contas
- `POST /contas` - Criar nova conta.
- `GET /contas` - Listar contas (filtros: `cliente_id`, `estado`, `tipo`).
- `GET /contas/{id}` - Obter detalhes da conta por ID.
- `PUT /contas/{id}` - Atualizar limite de crédito ou estado da conta.
- `POST /contas/{id}/encerrar` - Encerrar conta (Regra 7).
- `DELETE /contas/{id}` - Deletar conta encerrada.
- `GET /contas/{id}/extrato` - Extrato detalhado com histórico de transações.
- `GET /contas/{id}/tarifas` - Listar tarifas debitadas na conta.

### Cartões
- `POST /cartoes` - Emitir novo cartão vinculado a uma conta ativa.
- `GET /cartoes` - Listar cartões (filtros: `conta_id`, `estado`).
- `GET /cartoes/{id}` - Obter detalhes do cartão por ID.
- `PUT /cartoes/{id}` - Atualizar limite ou estado do cartão.
- `DELETE /cartoes/{id}` - Remover cartão sem pendências.
- `GET /cartoes/{id}/faturas` - Listar faturas do cartão (com cálculo dinâmico de juros).

### Transações
- `POST /transacoes/deposito` - Realizar depósito.
- `POST /transacoes/saque` - Realizar saque (Regras 1 e 2).
- `POST /transacoes/transferencia` - Realizar transferência (Regras 1, 2 e 3).
- `POST /transacoes/{id}/estorno` - Estornar transação em até 24h (Regra 4).
- `GET /transacoes/{id}` - Consultar transação por ID.

### Faturas
- `POST /faturas` - Lançar nova fatura para um cartão.
- `GET /faturas/{id}` - Consultar fatura por ID.
- `POST /faturas/{id}/pagamento` - Registrar pagamento de fatura.
- `POST /faturas/processar-atrasos` - Rotina de atualização de juros e bloqueio de cartões > 10 dias de atraso (Regra 5).

### Tarifas
- `POST /tarifas` - Lançar tarifa avulsa.
- `GET /tarifas` - Listar tarifas lançadas.
- `POST /tarifas/cobranca-mensal` - Rotina de cobrança da mensalidade por categoria.

### Relatórios Operacionais
- `GET /relatorios/clientes-maior-movimentacao` - Clientes com maior volume financeiro movimentado no período.
- `GET /relatorios/contas-saldo-negativo` - Relação de contas com saldo devedor e dias em atraso.
- `GET /relatorios/receita-tarifas-categoria` - Receita total arrecadada em tarifas discriminada por categoria.
- `POST /relatorios/processar-saldo-negativo-prolongado` - Rotina para bloqueio de clientes e cartões com saldo devedor superior a 30 dias (Regra 6).
