# API REST - Gestão de Biblioteca Universitária

API REST desenvolvida em Python para gestão completa de uma biblioteca universitária, implementando todas as regras de negócio para controle de acervo, usuários, empréstimos, devoluções, renovações, reservas com fila de espera, cálculo e perdão de multas, suspensões automáticas e relatórios estatísticos.

---

## 🛠️ Tecnologias Utilizadas

- **Linguagem:** Python 3.12+
- **Framework Web:** [FastAPI](https://fastapi.tiangolo.com/) (rápido, tipagem estática e documentação OpenAPI interativa em `/docs`)
- **Validação e Serialização:** [Pydantic v2](https://docs.pydantic.dev/)
- **ORM e Persistência:** [SQLAlchemy 2.0](https://www.sqlalchemy.org/) com banco relacional (SQLite com `PRAGMA foreign_keys = ON;`)
- **Testes Automatizados:** [Pytest](https://docs.pytest.org/) e TestClient (HTTPX)

---

## 🏛️ Entidades e Modelos de Dados

1. **Usuário (`Usuario`)**
   - `id`: Identificador único (chave primária)
   - `nome`: Nome completo
   - `email`: E-mail único e validado
   - `matricula`: Matrícula única
   - `categoria`: `aluno`, `professor` ou `visitante`
   - `situacao`: `ativo` ou `suspenso`
   - `data_fim_suspensao`: Data/hora de término da suspensão (quando aplicável)

2. **Livro (`Livro`)**
   - `id`: Identificador único
   - `titulo`: Título da obra
   - `autor`: Autor(es)
   - `isbn`: ISBN único
   - `ano`: Ano de publicação
   - `area_conhecimento`: Área do conhecimento (ex: Computação, Matemática, Física)

3. **Exemplar (`Exemplar`)**
   - Pertence a um Livro (`livro_id`)
   - `codigo_tombo`: Código de tombamento patrimonial único
   - `estado`: `disponivel`, `emprestado`, `reservado`, `em_reparo`, `baixado`

4. **Empréstimo (`Emprestimo`)**
   - Relaciona um Exemplar e um Usuário
   - `data_retirada`: Data/hora da retirada
   - `data_prevista`: Data/hora prevista para devolução
   - `data_devolucao`: Data/hora efetiva de entrega (nula enquanto ativo)
   - `estado`: `ativo`, `devolvido`, `atrasado`
   - `numero_renovacoes`: Contador de renovações efetuadas

5. **Reserva (`Reserva`)**
   - Relaciona um Livro e um Usuário
   - `data`: Data/hora de solicitação
   - `posicao_fila`: Posição ordinal na fila de espera
   - `estado`: `aguardando`, `disponivel`, `expirada`, `cancelada`
   - `data_disponibilizacao`: Data em que um exemplar ficou disponível para retirada
   - `data_limite_retirada`: Prazo de 48 horas para retirada

6. **Multa (`Multa`)**
   - Pertence a um Empréstimo
   - `valor`: Valor em reais (R$) com precisão decimal exata
   - `estado`: `aberta`, `paga`, `perdoada`
   - `data_geracao`: Data/hora de geração
   - `data_pagamento`: Data/hora de quitação

---

## 📋 Regras de Negócio Implementadas

### Parâmetros por Categoria de Usuário

| Categoria | Limite Exemplares | Prazo Empréstimo | Limite Renovações | Multa Diária | Teto Multa |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Aluno** | 3 exemplares | 7 dias | 2 renovações | R$ 1,00 / dia | R$ 30,00 |
| **Professor** | 8 exemplares | 30 dias | 4 renovações | R$ 0,50 / dia | R$ 50,00 |
| **Visitante** | 1 exemplar | 3 dias | 0 renovações | R$ 2,00 / dia | R$ 20,00 |

### Regras Sistêmicas

1. **Permissão de Empréstimo:** Só é concedido se o usuário estiver **ativo**, **sem nenhuma multa aberta** e **abaixo do seu limite de exemplares**.
2. **Suspensão por Atraso > 15 dias:** Usuário com atraso superior a 15 dias em qualquer empréstimo é **automaticamente suspenso**, e a suspensão dura o **dobro dos dias de atraso** (`2 * dias_atraso`).
3. **Condições de Renovação:** A renovação é negada se:
   - Houver fila de reserva para aquele livro (`aguardando` ou `disponivel`);
   - O empréstimo estiver atrasado;
   - O limite de renovações da categoria já tiver sido atingido.
4. **Fila de Reserva e Prazo de 48 Horas:**
   - A reserva entra numa fila por ordem de chegada;
   - Quando um exemplar é devolvido, o primeiro da fila passa ao estado `disponivel` e tem **48 horas para retirá-lo** (o exemplar passa a `reservado`);
   - Esgotado o prazo de 48h, a reserva torna-se `expirada` e a vez passa ao próximo da fila.
5. **Cálculo e Perdão de Multas:**
   - A multa acumula por dia corrido de atraso conforme a categoria, limitada rigorosamente ao teto;
   - Multa de **professor** é **perdoada automaticamente** (`estado = perdoada`) se o atraso for de **até 2 dias**.
6. **Exemplar em Reparo ou Baixado:**
   - Não pode ser emprestado nem reservado;
   - Se o último exemplar disponível de um livro for baixado, todas as reservas daquele livro são **automaticamente canceladas**.
7. **Atraso > 60 dias:**
   - Devolução de exemplar com mais de 60 dias de atraso **marca o exemplar como baixado**, aplica a suspensão correspondente ao dobro dos dias e **gera multa no valor do teto da categoria**.

---

## 🚀 Endpoints da API

### Usuários (`/usuarios`)
- `POST /usuarios` - Cadastra novo usuário (201 Created)
- `GET /usuarios` - Lista usuários (suporta filtros por `categoria`, `situacao`, paginação) (200 OK)
- `GET /usuarios/{id}` - Obtém detalhes do usuário (200 OK / 404 Not Found)
- `PUT /usuarios/{id}` - Atualiza dados do usuário (200 OK)
- `DELETE /usuarios/{id}` - Exclui usuário (204 No Content / 400 Bad Request se houver empréstimos ativos)

### Livros (`/livros`)
- `POST /livros` - Cadastra novo livro (201 Created / 409 Conflict se ISBN já existir)
- `GET /livros` - Lista livros (filtros por `titulo`, `autor`, `area_conhecimento`, `isbn`) (200 OK)
- `GET /livros/{id}` - Obtém dados de um livro (200 OK / 404 Not Found)
- `PUT /livros/{id}` - Atualiza livro (200 OK)
- `DELETE /livros/{id}` - Exclui livro (204 No Content / 400 Bad Request se houver exemplares emprestados)

### Exemplares (`/exemplares`)
- `POST /exemplares` - Cadastra exemplar vinculado a um livro (201 Created / 409 Conflict se tombo já existir)
- `GET /exemplares` - Lista exemplares (filtros por `livro_id`, `estado`) (200 OK)
- `GET /exemplares/{id}` - Obtém exemplar (200 OK)
- `PUT /exemplares/{id}` - Atualiza estado do exemplar (ex: `em_reparo`, `baixado`) (200 OK)
- `DELETE /exemplares/{id}` - Exclui exemplar (204 No Content)

### Empréstimos (`/emprestimos`)
- `POST /emprestimos` - Realiza novo empréstimo (201 Created / 400 Bad Request caso viole regras)
- `POST /emprestimos/{id}/renovar` - Renova empréstimo (200 OK / 400 Bad Request se atrasado, limite atingido ou com fila)
- `POST /emprestimos/{id}/devolver` - Devolve exemplar, calcula atrasos, suspensões e multas (200 OK)
- `GET /emprestimos/usuario/{usuario_id}` - Lista todos os empréstimos de um usuário (200 OK)
- `GET /emprestimos` - Lista todos os empréstimos (200 OK)
- `GET /emprestimos/{id}` - Detalhes de um empréstimo (200 OK)

### Reservas (`/reservas`)
- `POST /reservas` - Entra na fila de reserva de um livro (201 Created / 400 Bad Request / 409 Conflict)
- `POST /reservas/{id}/cancelar` - Cancela reserva voluntariamente (200 OK)
- `GET /reservas/livro/{livro_id}` - Lista fila de espera de um livro (200 OK)
- `POST /reservas/processar-expiracoes` - Verifica e expira reservas após prazo de 48h (200 OK)
- `GET /reservas` - Lista reservas gerais (200 OK)
- `GET /reservas/{id}` - Detalhes de uma reserva (200 OK)

### Multas (`/multas`)
- `GET /multas/usuario/{usuario_id}` - Lista multas de um usuário (200 OK)
- `POST /multas/{id}/pagar` - Registra pagamento da multa (200 OK / 400 Bad Request se já paga/perdoada)
- `GET /multas` - Lista todas as multas do sistema (200 OK)
- `GET /multas/{id}` - Detalhes de uma multa (200 OK)

### Relatórios (`/relatorios`)
- `GET /relatorios/livros-mais-emprestados` - Ranking de livros mais emprestados no período (`data_inicio`, `data_fim`, `limite`)
- `GET /relatorios/usuarios-mais-atrasos` - Usuários com mais atrasos e dias acumulados (`limite`)
- `GET /relatorios/taxa-ocupacao` - Taxa de ocupação percentual do acervo por área de conhecimento

---

## 🏃 Como Executar a Aplicação

### 1. Pré-requisitos
- Python 3.12+ instalado

### 2. Instalação das dependências
```bash
pip install -r requirements.txt
```

### 3. Execução do servidor
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 4. Acessando a documentação interativa
- **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 🧪 Como Executar os Testes Automatizados

A suíte de testes cobre todas as entidades, limites por categoria, regras de negócio e casos de borda:

```bash
pytest -v
```
