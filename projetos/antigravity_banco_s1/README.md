# API REST para Gestão de Contas Correntes Bancárias

API REST desenvolvida em Python com FastAPI e SQLAlchemy para gestão completa de contas correntes bancárias, cartões, faturas, transações financeiras, tarifas e relatórios operacionais.

---

## 📋 Sumário
- [Arquitetura e Tecnologias](#-arquitetura-e-tecnologias)
- [Entidades do Sistema](#-entidades-do-sistema)
- [Regras por Categoria de Cliente](#-regras-por-categoria-de-cliente)
- [Regras de Negócio Implementadas](#-regras-de-negócio-implementadas)
- [Estrutura do Projeto](#-estrutura-do-projeto)
- [Instalação e Execução](#-instalação-e-execução)
- [Execução dos Testes Automatizados](#-execução-dos-testes-automatizados)
- [Documentação dos Endpoints (Swagger / OpenAPI)](#-documentação-dos-endpoints)

---

## 🛠 Tecnologias
- **Linguagem**: Python 3.12+
- **Framework Web**: [FastAPI](https://fastapi.tiangolo.com/)
- **ORM / Banco de Dados**: [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (SQLite / PostgreSQL)
- **Validação de Dados**: [Pydantic v2](https://docs.pydantic.dev/) (com validação matemática estrita de dígitos de CPF)
- **Servidor ASGI**: [Uvicorn](https://www.uvicorn.org/)
- **Testes Automatizados**: [Pytest](https://docs.pytest.org/) & `TestClient`

---

## 🏛 Entidades do Sistema

1. **Cliente**:
   - `id`: Identificador único sequencial.
   - `nome`: Nome completo.
   - `cpf`: Cadastro de Pessoa Física único com validação algorítmica de 11 dígitos.
   - `email`: Endereço de e-mail único.
   - `categoria`: `comum`, `premium` ou `empresarial`.
   - `situacao`: `ativo` ou `bloqueado`.

2. **Conta**:
   - `id`: Identificador único.
   - `cliente_id`: Chave estrangeira para o cliente titular.
   - `numero`: Número único identificador da conta.
   - `tipo`: `corrente` ou `poupanca`.
   - `saldo`: Saldo atual da conta em precisão decimal.
   - `limite_credito`: Limite de crédito rotativo concedido.
   - `estado`: `ativa`, `bloqueada` ou `encerrada`.
   - `data_saldo_negativo`: Data/hora em que a conta ingressou em saldo devedor.

3. **Transação**:
   - `id`: Identificador único.
   - `conta_id`: Conta de origem/movimentada.
   - `conta_destino_id`: Conta destinatária (para transferências).
   - `tipo`: `deposito`, `saque`, `transferencia` ou `estorno`.
   - `valor`: Valor monetário da operação.
   - `data`: Timestamp UTC do registro.
   - `estado`: `pendente`, `efetivada` ou `estornada`.
   - `transacao_origem_id`: Vínculo para a transação original no caso de estorno.

4. **Cartão**:
   - `id`: Identificador único.
   - `conta_id`: Conta vinculada.
   - `numero`: Número identificador único do cartão.
   - `limite`: Limite de crédito do cartão.
   - `estado`: `ativo`, `bloqueado` ou `cancelado`.

5. **Fatura**:
   - `id`: Identificador único.
   - `cartao_id`: Cartão emissor da fatura.
   - `mes_referencia`: Mês de competência (`YYYY-MM`).
   - `valor`: Valor consolidado da fatura.
   - `valor_pago`: Total amortizado.
   - `juros_acumulados`: Encargos por atraso acumulados.
   - `data_vencimento`: Data limite de pagamento sem juros.
   - `data_pagamento`: Data/hora em que foi liquidada.
   - `estado`: `aberta`, `fechada`, `paga` ou `atrasada`.

6. **Tarifa**:
   - `id`: Identificador único.
   - `conta_id`: Conta cobrada.
   - `tipo`: Tipo do encargo (`mensalidade`, `transferencia`, etc.).
   - `valor`: Valor da tarifa.
   - `estado`: `pendente`, `cobrada` ou `isenta`.

---

## 🎯 Regras por Categoria de Cliente

| Categoria | Limite Diário de Saque | Limite por Transferência | Tarifa Mensal | Transações Isentas / Mês | Juros de Atraso |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Comum** | R$ 1.000,00 | R$ 5.000,00 | R$ 30,00 | 3 | 8% ao mês |
| **Premium** | R$ 5.000,00 | R$ 50.000,00 | R$ 0,00 (isenta) | Ilimitadas | 5% ao mês |
| **Empresarial** | R$ 20.000,00 | R$ 200.000,00 | R$ 120,00 | 50 | 3% ao mês |

---

## ⚙ Regras de Negócio

1. **Saque e Transferência em Conta Ativa de Cliente Ativo**:
   - Bloqueia saques ou transferências se o cliente estiver `bloqueado` ou a conta `bloqueada` ou `encerrada`.
   - Limite diário de saque acumulado no dia civil respeita rigorosamente a categoria.
   - Limite individual por transferência respeita o teto da categoria.

2. **Saldo Negativo até o Limite de Crédito**:
   - Operações que levem o saldo abaixo de `-limite_credito` são recusadas com HTTP 400.
   - Quando o saldo entra no negativo, o sistema grava `data_saldo_negativo`. Ao retornar a $\ge 0$, o marcador é limpo.

3. **Franquia de Transferências e Cobrança de Tarifas**:
   - Transferências entre contas do **mesmo cliente** são isentas e não gastam a franquia mensal.
   - Transferências para **outros clientes** consomem a franquia mensal da categoria. Ao esgotar a franquia, é cobrada tarifa avulsa de transferência (R$ 10,00) debitada do saldo da conta origem.

4. **Estorno em até 24 Horas**:
   - Transações com `estado == 'efetivada'` podem ser estornadas dentro de 24 horas.
   - Reverte os saldos das contas envolvidas.
   - Marca a transação original como `estornada` e cria um novo registro com tipo `estorno`.

5. **Faturas Atrasadas e Bloqueio de Cartão**:
   - Faturas não quitadas após a data de vencimento passam para o estado `atrasada` e acumulam juros pro-rata conforme a taxa mensal da categoria.
   - Faturas com **mais de 10 dias de atraso** bloqueiam automaticamente o respectivo cartão (`cartao.estado = 'bloqueado'`).

6. **Inadimplência de Conta (> 30 dias negativa)**:
   - Contas com saldo negativo contínuo por mais de 30 dias acionam o bloqueio cadastral do cliente (`cliente.situacao = 'bloqueado'`) e bloqueiam **todos os cartões** vinculados a qualquer conta do cliente.

7. **Encerramento de Conta**:
   - Exige que o saldo seja exatamente `R$ 0,00`.
   - Exige que não haja faturas em aberto (`aberta`, `fechada` ou `atrasada`).
   - Ao ser encerrada, todos os cartões vinculados à conta são imediatamente alterados para `cancelado`.

---

## 📂 Estrutura do Projeto

```
antigravity_banco_s1/
├── app/
│   ├── config.py              # Configurações gerais e regras numéricas de categorias
│   ├── database.py            # Inicialização do banco relacional (SQLAlchemy)
│   ├── main.py                # Instância do FastAPI, middleware e exception handlers
│   ├── models/                # Modelos ORM
│   │   ├── cliente.py
│   │   ├── conta.py
│   │   ├── transacao.py
│   │   ├── cartao.py
│   │   ├── fatura.py
│   │   └── tarifa.py
│   ├── schemas/               # Schemas de validação e serialização Pydantic
│   │   ├── common.py          # Validador de CPF algorítmico
│   │   ├── cliente.py
│   │   ├── conta.py
│   │   ├── transacao.py
│   │   ├── cartao.py
│   │   ├── fatura.py
│   │   ├── tarifa.py
│   │   └── relatorio.py
│   ├── services/              # Camada de regras de negócio
│   │   ├── cliente_service.py
│   │   ├── conta_service.py
│   │   ├── cartao_service.py
│   │   ├── transacao_service.py
│   │   ├── fatura_service.py
│   │   ├── tarifa_service.py
│   │   ├── relatorio_service.py
│   │   └── rotina_service.py
│   └── routers/               # Endpoints REST
│       ├── clientes.py
│       ├── contas.py
│       ├── cartoes.py
│       ├── transacoes.py
│       ├── faturas.py
│       ├── tarifas.py
│       ├── relatorios.py
│       └── rotinas.py
├── tests/                     # Suite de testes automatizados com Pytest
│   ├── conftest.py
│   ├── test_clientes.py
│   ├── test_contas.py
│   ├── test_cartoes.py
│   ├── test_transacoes.py
│   ├── test_regras_negocio.py # Testes exaustivos das 7 regras e categorias
│   ├── test_faturas.py
│   ├── test_tarifas.py
│   └── test_relatorios.py
├── pytest.ini
├── requirements.txt
└── README.md
```

---

## 🚀 Instalação e Execução

### 1. Criar e ativar ambiente virtual (opcional)
```bash
python -m venv venv
# No Windows:
.\venv\Scripts\activate
# No Linux/Mac:
source venv/bin/activate
```

### 2. Instalar dependências
```bash
pip install -r requirements.txt
```

### 3. Iniciar o servidor de desenvolvimento
```bash
uvicorn app.main:app --reload --port 8000
```

A API estará acessível em `http://127.0.0.1:8000`.

---

## 🧪 Execução dos Testes Automatizados

Para rodar todos os testes com cobertura detalhada:
```bash
python -m pytest -v
```

---

## 📖 Documentação dos Endpoints

Com a aplicação em execução, acesse no navegador:
- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Redoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

### Principais Rotas Disponíveis

#### Clientes
- `POST /clientes`: Cadastro de cliente (valida CPF algorítmico e unicidade de email/CPF).
- `GET /clientes`: Listagem de clientes com filtros por categoria e situação.
- `GET /clientes/{id}`: Detalhes do cliente.
- `PUT /clientes/{id}`: Atualização cadastral.
- `DELETE /clientes/{id}`: Remoção de cliente (exige contas zeradas).

#### Contas
- `POST /contas`: Abertura de conta.
- `GET /contas`: Listagem de contas com filtros por cliente e estado.
- `GET /contas/{id}`: Detalhes da conta.
- `PUT /contas/{id}`: Atualização de limite ou tipo.
- `POST /contas/{id}/encerrar`: Encerramento da conta (Regra 7).

#### Cartões
- `POST /cartoes`: Emissão de cartão vinculado a uma conta.
- `GET /cartoes`: Listagem de cartões.
- `GET /cartoes/{id}`: Detalhes do cartão.
- `PUT /cartoes/{id}`: Atualização de limite ou estado.
- `DELETE /cartoes/{id}`: Cancelamento de cartão.

#### Transações
- `POST /transacoes/deposito`: Depósito em conta.
- `POST /transacoes/saque`: Saque com validação de limite diário e crédito (Regras 1 e 2).
- `POST /transacoes/transferencia`: Transferência com franquia e tarifa (Regras 1, 2 e 3).
- `POST /transacoes/{id}/estorno`: Estorno em até 24h revertendo saldos (Regra 4).
- `GET /contas/{id}/extrato`: Extrato completo com filtros de período e tipo.

#### Faturas
- `POST /cartoes/{id}/faturas`: Geração de fatura.
- `GET /cartoes/{id}/faturas`: Listagem de faturas por cartão.
- `POST /faturas/{id}/pagamento`: Quitação total ou parcial (opção de débito em conta).
- `POST /faturas/verificar-atrasos`: Rotina de aplicação de juros e bloqueio de cartão após 10 dias (Regra 5).

#### Tarifas
- `GET /contas/{id}/tarifas`: Listagem de tarifas por conta.
- `POST /contas/{id}/tarifas/cobrar-mensalidade`: Aplicação da mensalidade da categoria.

#### Relatórios
- `GET /relatorios/maior-movimentacao`: Ranking de clientes com maior volume financeiro no período.
- `GET /relatorios/contas-saldo-negativo`: Relação de contas com saldo devedor e dias no negativo.
- `GET /relatorios/receita-tarifas`: Demonstrativo de receitas por categoria de cliente.

#### Rotinas de Manutenção
- `POST /rotinas/verificar-inadimplencia`: Processa faturas em atraso (Regra 5) e bloqueia clientes/cartões com mais de 30 dias de saldo negativo (Regra 6).
