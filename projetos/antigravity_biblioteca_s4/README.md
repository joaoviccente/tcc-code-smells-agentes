# API de Gestão de Biblioteca Universitária

API RESTful completa em Python para gestão de biblioteca universitária, desenvolvida com **FastAPI**, **SQLAlchemy** e **Pydantic**. Inclui validação estrita de dados, persistência em banco relacional, códigos de status HTTP apropriados e cobertura integral de testes automatizados com **pytest**.

---

## 🚀 Como Executar o Projeto

### 1. Pré-requisitos
- Python 3.10 ou superior
- Gerenciador de pacotes `pip`

### 2. Instalação das Dependências
```bash
pip install -r requirements.txt
```

### 3. Execução do Servidor
```bash
uvicorn app.main:app --reload --port 8000
```
- A API estará disponível em: `http://localhost:8000`
- Documentação interativa Swagger/OpenAPI: `http://localhost:8000/docs`
- Documentação alternativa Redoc: `http://localhost:8000/redoc`

### 4. Execução dos Testes Automatizados
```bash
python -m pytest -v
```

---

## 🏛️ Entidades do Sistema

1. **Usuário (`Usuario`)**
   - `id`: Identificador único (chave primária)
   - `nome`: Nome do usuário
   - `email`: E-mail único com validação de formato
   - `matricula`: Código de matrícula único
   - `categoria`: `aluno`, `professor` ou `visitante`
   - `situacao`: `ativo` ou `suspenso`
   - `data_fim_suspensao`: Data e hora do término da suspensão (calculada automaticamente)

2. **Livro (`Livro`)**
   - `id`: Identificador único
   - `titulo`: Título da obra
   - `autor`: Autor da obra
   - `isbn`: Código ISBN
   - `ano`: Ano de publicação
   - `area_conhecimento`: Área de conhecimento (ex: Computação, Matemática, Engenharia)

3. **Exemplar (`Exemplar`)**
   - `id`: Identificador único
   - `livro_id`: Referência ao livro pertencente
   - `codigo_tombo`: Código patrimonial único
   - `estado`: `disponivel`, `emprestado`, `reservado`, `em_reparo` ou `baixado`

4. **Empréstimo (`Emprestimo`)**
   - `id`: Identificador único
   - `exemplar_id`: Exemplar retirado
   - `usuario_id`: Usuário responsável
   - `data_retirada`: Data e hora da retirada
   - `data_prevista`: Data prevista para devolução (calculada por categoria)
   - `data_devolucao`: Data e hora da devolução efetiva
   - `estado`: `ativo`, `devolvido` ou `atrasado`
   - `numero_de_renovacoes`: Quantidade de renovações já realizadas

5. **Reserva (`Reserva`)**
   - `id`: Identificador único
   - `livro_id`: Livro reservado
   - `usuario_id`: Usuário solicitante
   - `data`: Data e hora do pedido de reserva
   - `posicao_na_fila`: Posição ordinal na fila de espera (1, 2, 3...)
   - `estado`: `aguardando`, `disponivel`, `expirada`, `cancelada` (ou `concluida`)
   - `data_limite_retirada`: Prazo de 48h para retirada após disponibilização
   - `exemplar_id`: Exemplar reservado alocado

6. **Multa (`Multa`)**
   - `id`: Identificador único
   - `emprestimo_id`: Empréstimo associado
   - `valor`: Valor monetário da multa em Reais (R$)
   - `estado`: `aberta`, `paga` ou `perdoada`

---

## 📋 Regras por Categoria de Usuário

| Categoria | Limite de Exemplares | Prazo de Devolução | Limite de Renovações | Multa por Dia | Teto da Multa | Regra Especial de Perdão |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Aluno** | 3 exemplares | 7 dias corridos | 2 renovações | R$ 1,00 / dia | R$ 30,00 | — |
| **Professor** | 8 exemplares | 30 dias corridos | 4 renovações | R$ 0,50 / dia | R$ 50,00 | Multa perdoada automaticamente se atraso de até 2 dias |
| **Visitante** | 1 exemplar | 3 dias corridos | 0 renovações | R$ 2,00 / dia | R$ 20,00 | — |

---

## ⚙️ Regras de Negócio Implementadas

1. **Permissão de Empréstimo:**
   - Empréstimo só é permitido se o usuário estiver ativo (`situacao == 'ativo'`).
   - O usuário não pode possuir nenhuma multa em estado `aberta`.
   - A quantidade de exemplares com empréstimos ativos/atrasados deve estar estritamente abaixo do limite da categoria.
   - Exemplares em estado `em_reparo` ou `baixado` não podem ser emprestados (HTTP 400).

2. **Suspensão Automática por Atraso:**
   - Atraso superior a 15 dias corridos (> 15 dias) em qualquer empréstimo suspende automaticamente o usuário.
   - A duração da suspensão é o dobro dos dias de atraso (`2 * dias_atraso`).
   - O término da suspensão é gerenciado dinamicamente no campo `data_fim_suspensao`.

3. **Renovação de Empréstimo:**
   - Negada se houver reservas na fila (`aguardando` ou `disponivel`) para aquele livro.
   - Negada se o empréstimo estiver atrasado (`data_atual > data_prevista` ou `estado == 'atrasado'`).
   - Negada se o número de renovações já tiver atingido o limite da categoria.
   - Em caso de sucesso, estende a data prevista pelo prazo regulamentar da categoria.

4. **Fila de Reserva e Janela de 48 Horas:**
   - As reservas entram na fila por ordem de chegada (FIFO).
   - Quando um exemplar é devolvido, o primeiro da fila passa ao estado `disponivel`, o exemplar assume o estado `reservado` e é concedido o prazo de 48 horas para retirada.
   - Esgotado o prazo de 48 horas sem retirada, a reserva é marcada como `expirada` e a vez passa imediatamente ao próximo da fila. Caso a fila esteja vazia, o exemplar retorna a `disponivel`.

5. **Cálculo de Multas:**
   - A multa acumula por dia corrido de atraso multiplicado pelo valor diário da categoria, limitada ao teto estabelecido.
   - Empréstimos de professor devolvidos com até 2 dias de atraso têm a multa gerada automaticamente com estado `perdoada`.

6. **Restrições de Exemplar e Baixa do Acervo:**
   - Exemplar em reparo ou baixado não pode ser emprestado nem reservado.
   - Se o último exemplar não-baixado de um livro for marcado como `baixado`, todas as reservas em aberto para aquele livro são automaticamente canceladas (`cancelada`).

7. **Devolução com Mais de 60 Dias de Atraso:**
   - Devolução com atraso superior a 60 dias (> 60 dias) marca imediatamente o exemplar como `baixado`.
   - Gera multa aberta no valor exato do teto da categoria do usuário.
   - Aplica a suspensão automática da Regra 2 (`2 * dias_atraso`).
   - Caso tenha sido o último exemplar ativo do livro, cancela as reservas do livro (Regra 6).

---

## 📡 Catálogo de Endpoints

Todos os endpoints estão disponíveis tanto na raiz (ex: `/usuarios`) quanto sob o prefixo `/api` (ex: `/api/usuarios`).

### 👤 Usuários
- `POST /usuarios`: Cadastra novo usuário (HTTP 201).
- `GET /usuarios`: Lista usuários com filtros opcionais por categoria e situação (HTTP 200).
- `GET /usuarios/{id}`: Obtém detalhes de um usuário (HTTP 200 / 404).
- `PUT /usuarios/{id}`: Atualiza dados cadastrais de um usuário (HTTP 200 / 404 / 409).
- `DELETE /usuarios/{id}`: Remove usuário se não possuir empréstimos ativos (HTTP 204 / 400 / 404).
- `GET /usuarios/{id}/emprestimos`: Lista empréstimos do usuário (HTTP 200).
- `GET /usuarios/{id}/multas`: Lista multas do usuário (HTTP 200).

### 📚 Livros
- `POST /livros`: Cadastra novo livro (HTTP 201).
- `GET /livros`: Lista livros com filtros por título, autor, ISBN e área de conhecimento (HTTP 200).
- `GET /livros/{id}`: Obtém detalhes de um livro (HTTP 200 / 404).
- `PUT /livros/{id}`: Atualiza dados de um livro (HTTP 200 / 404).
- `DELETE /livros/{id}`: Remove livro se não possuir empréstimos ativos (HTTP 204 / 400 / 404).
- `GET /livros/{id}/exemplares`: Lista exemplares vinculados ao livro (HTTP 200).
- `GET /livros/{id}/reservas`: Lista fila de reservas do livro (HTTP 200).

### 📖 Exemplares
- `POST /exemplares`: Cadastra novo exemplar com código de tombo único (HTTP 201 / 409).
- `GET /exemplares`: Lista exemplares com filtros por `livro_id` e `estado` (HTTP 200).
- `GET /exemplares/{id}`: Obtém exemplar por ID (HTTP 200 / 404).
- `PUT /exemplares/{id}`: Atualiza exemplar (se baixado, verifica cancelamento de reservas) (HTTP 200 / 404 / 409).
- `DELETE /exemplares/{id}`: Remove exemplar sem empréstimos ativos (HTTP 204 / 400 / 404).

### 🔄 Empréstimos
- `POST /emprestimos`: Realiza empréstimo respeitando limites, multas e disponibilidade (HTTP 201 / 400 / 404).
- `POST /emprestimos/{id}/renovar`: Renova empréstimo ativo (HTTP 200 / 400 / 404).
- `POST /emprestimos/{id}/devolver`: Registra devolução, calcula multas e dispara reservas (HTTP 200 / 400 / 404).
- `GET /emprestimos`: Lista todos os empréstimos com filtros (HTTP 200).
- `GET /emprestimos/{id}`: Obtém empréstimo por ID (HTTP 200 / 404).
- `GET /emprestimos/usuario/{usuario_id}`: Lista empréstimos de um usuário específico (HTTP 200).

### 🔖 Reservas
- `POST /reservas`: Cria reserva e insere na fila de espera por ordem de chegada (HTTP 201 / 400 / 404).
- `POST /reservas/{id}/cancelar`: Cancela reserva e avança a fila (HTTP 200 / 400 / 404).
- `GET /reservas/livro/{livro_id}`: Lista fila de espera ativa de um livro (HTTP 200).
- `GET /reservas`: Lista todas as reservas com filtros (HTTP 200).
- `GET /reservas/{id}`: Obtém reserva por ID (HTTP 200 / 404).
- `POST /reservas/processar-expiracoes`: Rotina que expira reservas > 48h e avança fila (HTTP 200).

### 💰 Multas
- `GET /multas`: Lista multas com filtros opcionais (HTTP 200).
- `GET /multas/{id}`: Obtém detalhes de uma multa (HTTP 200 / 404).
- `GET /multas/usuario/{usuario_id}`: Lista histórico de multas do usuário (HTTP 200).
- `POST /multas/{id}/pagar`: Registra pagamento de multa aberta (HTTP 200 / 400 / 404).

### 📊 Relatórios
- `GET /relatorios/livros-mais-emprestados?data_inicio=YYYY-MM-DD&data_fim=YYYY-MM-DD`: Livros mais emprestados no período (HTTP 200).
- `GET /relatorios/usuarios-mais-atrasos`: Usuários com maior número de empréstimos em atraso (HTTP 200).
- `GET /relatorios/taxa-ocupacao`: Taxa percentual de ocupação do acervo por área de conhecimento (HTTP 200).
