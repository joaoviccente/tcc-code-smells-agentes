# API REST de Gestão de Biblioteca Universitária

API REST desenvolvida em Python (FastAPI, SQLAlchemy e Pydantic v2) para gestão completa de biblioteca universitária, com controle de usuários, acervo de livros e exemplares, empréstimos, renovações, filas de espera para reservas, multas e relatórios estatísticos.

---

## 🏛️ Entidades do Domínio

1. **Usuário (`Usuario`)**
   - `id`: Identificador numérico único
   - `nome`: Nome completo
   - `email`: Endereço de e-mail (único)
   - `matricula`: Código de matrícula institucional (único)
   - `categoria`: `aluno`, `professor`, `visitante`
   - `situacao`: `ativo`, `suspenso`
   - `suspenso_ate`: Data e hora do término da suspensão (calculada automaticamente)

2. **Livro (`Livro`)**
   - `id`: Identificador numérico único
   - `titulo`: Título da obra
   - `autor`: Autor da obra
   - `isbn`: Código ISBN (único)
   - `ano`: Ano de publicação
   - `area_conhecimento`: Área do conhecimento

3. **Exemplar (`Exemplar`)**
   - `id`: Identificador numérico único
   - `livro_id`: Chave estrangeira para `Livro`
   - `codigo_tombo`: Código de tombamento patrimonial (único)
   - `estado`: `disponivel`, `emprestado`, `reservado`, `em_reparo`, `baixado`

4. **Empréstimo (`Emprestimo`)**
   - `id`: Identificador numérico único
   - `exemplar_id`: Chave estrangeira para `Exemplar`
   - `usuario_id`: Chave estrangeira para `Usuario`
   - `data_retirada`: Data e hora da retirada
   - `data_prevista`: Data e hora prevista para devolução
   - `data_devolucao`: Data e hora em que foi efetivamente devolvido (nulo enquanto ativo)
   - `estado`: `ativo`, `devolvido`, `atrasado`
   - `numero_renovacoes`: Quantidade de renovações já realizadas

5. **Reserva (`Reserva`)**
   - `id`: Identificador numérico único
   - `livro_id`: Chave estrangeira para `Livro`
   - `usuario_id`: Chave estrangeira para `Usuario`
   - `data_reserva`: Data e hora em que a reserva foi solicitada
   - `posicao_fila`: Posição ordinal na fila de espera (1, 2, 3...)
   - `estado`: `aguardando`, `disponivel`, `expirada`, `cancelada`, `concluida`
   - `data_disponibilizacao`: Data e hora em que um exemplar ficou disponível para o usuário
   - `exemplar_id`: Chave estrangeira do exemplar reservado especificamente para o usuário

6. **Multa (`Multa`)**
   - `id`: Identificador numérico único
   - `emprestimo_id`: Chave estrangeira para `Emprestimo`
   - `valor`: Valor monetário da multa em Reais (R$)
   - `estado`: `aberta`, `paga`, `perdoada`
   - `data_geracao`: Data de lançamento da multa
   - `data_pagamento`: Data de quitação da multa

---

## 📋 Regras por Categoria de Usuário

| Categoria | Limite de Exemplares | Prazo do Empréstimo | Limite de Renovações | Multa Diária | Teto da Multa |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Aluno** | 3 exemplares | 7 dias | 2 renovações | R$ 1,00 / dia | R$ 30,00 |
| **Professor** | 8 exemplares | 30 dias | 4 renovações | R$ 0,50 / dia | R$ 50,00 |
| **Visitante** | 1 exemplar | 3 dias | Nenhuma (0) | R$ 2,00 / dia | R$ 20,00 |

---

## ⚖️ Regras de Negócio

1. **Permissão de Empréstimo**:
   - Empréstimo só é permitido a usuário com situação `ativo`.
   - Usuário não pode possuir nenhuma multa com estado `aberta`.
   - Quantidade de empréstimos ativos do usuário deve estar estritamente abaixo do limite de sua categoria.
   - O exemplar deve estar `disponivel` (ou `reservado` exclusivamente para o próprio usuário que está realizando a retirada).

2. **Suspensão Automática por Atraso (> 15 dias)**:
   - Usuário com atraso superior a 15 dias corridos em qualquer empréstimo é automaticamente suspenso.
   - A suspensão dura **o dobro dos dias de atraso** (`2 * dias_atraso`).
   - Durante a suspensão, o usuário é impedido de realizar novos empréstimos ou reservas.

3. **Renovação de Empréstimo**:
   - A renovação é negada caso o empréstimo esteja em atraso.
   - A renovação é negada caso exista fila de espera de reserva para o livro.
   - A renovação é negada caso o limite de renovações da categoria do usuário já tenha sido atingido.
   - Quando concedida, a nova data prevista é estendida pelo prazo da categoria e o contador de renovações é incrementado.

4. **Fila de Reserva e Notificação (48 horas)**:
   - Novas reservas entram na fila por estrita ordem de chegada (`data_reserva`).
   - Quando um exemplar é devolvido, o primeiro usuário da fila passa ao estado `disponivel`, o exemplar transita para `reservado` e o usuário tem **48 horas** para retirá-lo.
   - Esgotado o prazo de 48 horas sem retirada, a reserva é marcada como `expirada` e a oportunidade é automaticamente transferida para o próximo da fila.

5. **Multa por Atraso**:
   - A multa acumula por dia corrido de atraso, calculada segundo o valor diário da categoria e limitada ao teto estipulado.
   - Multa de **professor é perdoada automaticamente** se o atraso for de até 2 dias corridos (`estado = perdoada`).

6. **Exemplar em Reparo ou Baixado**:
   - Exemplar nos estados `em_reparo` ou `baixado` não pode ser emprestado nem reservado.
   - Se o último exemplar ativo/disponível de um livro for baixado, todas as reservas ativas daquele livro são automaticamente canceladas.

7. **Devolução com Atraso Extremo (> 60 dias)**:
   - Devolução de exemplar com mais de 60 dias de atraso marca o exemplar imediatamente como `baixado`.
   - Gera multa no valor do teto da categoria do usuário.
   - Suspende o usuário pelo dobro dos dias de atraso (`2 * dias_atraso`).
   - Se era o último exemplar do livro, cancela as reservas pendentes daquele livro.

---

## 🚀 Endpoints da API

### Usuários
- `POST /usuarios`: Cadastra um novo usuário (HTTP 201).
- `GET /usuarios`: Lista usuários, com filtros opcionais por `categoria` e `situacao`.
- `GET /usuarios/{id}`: Obtém detalhes de um usuário por ID.
- `PUT /usuarios/{id}`: Atualiza os dados de um usuário.
- `DELETE /usuarios/{id}`: Remove um usuário (bloqueado se houver empréstimos ativos ou multas em aberto - HTTP 204).

### Livros
- `POST /livros`: Cadastra um livro (HTTP 201).
- `GET /livros`: Lista livros, com busca por `titulo`, `autor`, `isbn` ou `area_conhecimento`.
- `GET /livros/{id}`: Obtém detalhes de um livro por ID.
- `PUT /livros/{id}`: Atualiza dados de um livro.
- `DELETE /livros/{id}`: Remove um livro (bloqueado se houver exemplares emprestados - HTTP 204).

### Exemplares
- `POST /exemplares`: Cadastra um novo exemplar vinculado a um livro (HTTP 201).
- `GET /exemplares`: Lista exemplares, com filtros opcionais por `livro_id` e `estado`.
- `GET /exemplares/{id}`: Obtém detalhes de um exemplar.
- `PUT /exemplares/{id}`: Atualiza dados ou estado do exemplar (se baixado, aplica Regra 6).
- `DELETE /exemplares/{id}`: Remove exemplar (bloqueado se emprestado - HTTP 204).

### Empréstimos
- `POST /emprestimos`: Realiza um empréstimo (HTTP 201).
  - Body: `{"usuario_id": 1, "exemplar_id": 2, "data_retirada": "2026-11-10T10:00:00"}` (data opcional).
- `POST /emprestimos/{id}/renovar`: Renova o empréstimo (HTTP 200).
- `POST /emprestimos/{id}/devolver`: Registra a devolução do exemplar (HTTP 200).
  - Body: `{"data_devolucao": "2026-11-17T10:00:00"}` (data opcional).
- `GET /emprestimos/usuario/{usuario_id}`: Lista o histórico e empréstimos ativos de um usuário.
- `GET /emprestimos`: Lista todos os empréstimos (filtro por `estado`).

### Reservas
- `POST /reservas`: Cria uma reserva para um livro (HTTP 201).
  - Body: `{"usuario_id": 1, "livro_id": 1}`.
- `POST /reservas/{id}/cancelar`: Cancela uma reserva e reorganiza a fila (HTTP 200).
- `GET /reservas/livro/{livro_id}`: Lista a fila de reservas ativas de um livro, por ordem de prioridade.
- `GET /reservas`: Lista todas as reservas cadastradas.

### Multas
- `GET /multas/usuario/{usuario_id}`: Lista todas as multas de um usuário.
- `POST /multas/{id}/pagar`: Registra a quitação de uma multa aberta (HTTP 200).
- `GET /multas`: Lista todas as multas do sistema.

### Relatórios
- `GET /relatorios/livros-mais-emprestados?data_inicio=...&data_fim=...&limite=10`: Livros com maior número de empréstimos no intervalo informado.
- `GET /relatorios/usuarios-mais-atrasos?limite=10`: Usuários com maior histórico de atrasos em devoluções.
- `GET /relatorios/taxa-ocupacao`: Taxa de ocupação percentual do acervo agrupada por área do conhecimento.

---

## 🛠️ Tecnologias Utilizadas

- **Linguagem**: Python 3.12+
- **Framework Web**: FastAPI
- **Servidor ASGI**: Uvicorn
- **ORM / Banco Relacional**: SQLAlchemy com SQLite
- **Validação de Schemas**: Pydantic v2 (com suporte a `EmailStr` e `ConfigDict`)
- **Testes Automatizados**: Pytest e HTTPX (Starlette TestClient)

---

## ⚙️ Instalação e Execução

### 1. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 2. Executar a Aplicação
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Acesse a documentação interativa Swagger UI em:
👉 **http://localhost:8000/docs**

Ou Redoc em:
👉 **http://localhost:8000/redoc**

### 3. Executar os Testes Automatizados
```bash
python -m pytest -v
```
