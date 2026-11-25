# API REST de Gestão de Biblioteca Universitária

API REST completa desenvolvida em Python com **FastAPI**, **SQLAlchemy** e **Pydantic v2** para gestão de uma biblioteca universitária, implementando todas as regras de negócio, limites por categoria, controle de filas de reserva, cálculo de multas e relatórios analíticos.

---

## 🏛️ Arquitetura e Estrutura do Projeto

O projeto segue as melhores práticas de Clean Architecture e separação de responsabilidades:

```text
antigravity_biblioteca_s3/
├── app/
│   ├── config.py              # Definições de regras, limites e constantes
│   ├── database.py            # Configuração do banco relacional (SQLAlchemy)
│   ├── utils.py               # Utilitários de data/hora (compatível com UTC/Python 3.12+)
│   ├── models/                # Modelos ORM relacionais
│   │   ├── enums.py           # Enumerações oficiais das entidades
│   │   ├── usuario.py         # Entidade Usuario
│   │   ├── livro.py           # Entidade Livro
│   │   ├── exemplar.py        # Entidade Exemplar
│   │   ├── emprestimo.py      # Entidade Emprestimo
│   │   ├── reserva.py         # Entidade Reserva
│   │   └── multa.py           # Entidade Multa
│   ├── schemas/               # Modelos Pydantic para validação e serialização
│   │   ├── usuario.py
│   │   ├── livro.py
│   │   ├── exemplar.py
│   │   ├── emprestimo.py
│   │   ├── reserva.py
│   │   ├── multa.py
│   │   └── relatorio.py
│   ├── services/              # Camada de lógica e regras de negócio
│   │   ├── usuario_service.py
│   │   ├── livro_service.py
│   │   ├── exemplar_service.py
│   │   ├── emprestimo_service.py
│   │   ├── reserva_service.py
│   │   ├── multa_service.py
│   │   └── relatorio_service.py
│   ├── routers/               # Endpoints REST e controle de status HTTP
│   │   ├── usuarios.py
│   │   ├── livros.py
│   │   ├── exemplares.py
│   │   ├── emprestimos.py
│   │   ├── reservas.py
│   │   ├── multas.py
│   │   └── relatorios.py
│   └── main.py                # Inicialização da aplicação FastAPI
├── tests/                     # Suite abrangente de testes automatizados com pytest
│   ├── conftest.py
│   ├── test_usuarios.py
│   ├── test_livros.py
│   ├── test_exemplares.py
│   ├── test_emprestimos.py
│   ├── test_reservas.py
│   ├── test_multas.py
│   ├── test_relatorios.py
│   └── test_casos_especiais.py
├── requirements.txt
├── run.py
└── README.md
```

---

## 📋 Entidades e Atributos

| Entidade | Atributos |
|---|---|
| **Usuario** | `id`, `nome`, `email` (único), `matricula` (única), `categoria` (`aluno`, `professor`, `visitante`), `situacao` (`ativo`, `suspenso`), `data_suspensao_fim` |
| **Livro** | `id`, `titulo`, `autor`, `isbn` (único), `ano`, `area` (área de conhecimento) |
| **Exemplar** | `id`, `livro_id`, `codigo_tombo` (único), `estado` (`disponivel`, `emprestado`, `reservado`, `em_reparo`, `baixado`) |
| **Emprestimo** | `id`, `exemplar_id`, `usuario_id`, `data_retirada`, `data_prevista`, `data_devolucao`, `estado` (`ativo`, `devolvido`, `atrasado`), `numero_renovacoes` |
| **Reserva** | `id`, `livro_id`, `usuario_id`, `exemplar_id`, `data`, `posicao_fila`, `estado` (`aguardando`, `disponivel`, `expirada`, `cancelada`), `data_limite_retirada` |
| **Multa** | `id`, `emprestimo_id` (único), `valor`, `estado` (`aberta`, `paga`, `perdoada`), `data_geracao`, `data_pagamento` |

---

## ⚖️ Regras por Categoria de Usuário

| Categoria | Limite de Exemplares | Prazo de Devolução | Limite de Renovações | Multa Diária | Teto da Multa |
|---|:---:|:---:|:---:|:---:|:---:|
| **Aluno** | 3 exemplares | 7 dias | 2 renovações | R$ 1,00 / dia | R$ 30,00 |
| **Professor** | 8 exemplares | 30 dias | 4 renovações | R$ 0,50 / dia | R$ 50,00 |
| **Visitante** | 1 exemplar | 3 dias | 0 renovações | R$ 2,00 / dia | R$ 20,00 |

---

## ⚙️ Regras de Negócio Implementadas

1. **Elegibilidade para Empréstimo:**
   - Permitido apenas para usuário com situação `ativo`, sem nenhuma multa com estado `aberta` e que ainda não atingiu o limite de exemplares da sua categoria (Aluno: 3, Professor: 8, Visitante: 1).
2. **Suspensão Automática por Atraso (> 15 dias):**
   - Usuário com atraso superior a 15 dias em qualquer empréstimo é automaticamente suspenso (`situacao = 'suspenso'`).
   - A suspensão dura **o dobro dos dias de atraso** (`dias_atraso * 2`).
3. **Condições para Renovação:**
   - Renovação negada se houver reservas na fila para aquele livro (`aguardando` ou `disponivel`), se o empréstimo estiver atrasado (`now > data_prevista`) ou se o limite de renovações da categoria tiver sido atingido (Aluno: 2, Professor: 4, Visitante: 0).
4. **Fila de Reservas e Janela de 48 Horas:**
   - Reservas entram em fila por ordem de chegada (`data` ASC, `posicao_fila`).
   - Quando um exemplar é devolvido, o 1º da fila passa ao estado `disponivel` e o exemplar fica `reservado`, iniciando a contagem de 48 horas (`data_limite_retirada = data_devolucao + 48h`).
   - Esgotado o prazo de 48h sem retirada, a reserva expira (`expirada`) e a vez passa para o próximo da fila.
5. **Cálculo de Multas e Perdão para Professor:**
   - Multa calculada por dia corrido de atraso de acordo com a categoria, limitada ao teto.
   - Multa de professor com **até 2 dias de atraso é automaticamente perdoada** (`estado = 'perdoada'`). Atrasos superiores a 2 dias geram multa com estado `aberta` (R$ 0,50/dia até R$ 50,00).
6. **Restrições de Exemplar e Cancelamento em Massa:**
   - Exemplar em estado `em_reparo` ou `baixado` não pode ser emprestado nem reservado.
   - Se o último exemplar de um livro for marcado como `baixado`, todas as reservas ativas daquele livro são automaticamente canceladas (`estado = 'cancelada'`).
7. **Extravio / Atraso Crítico (> 60 dias):**
   - Devolução de exemplar com mais de 60 dias de atraso marca o exemplar imediatamente como `baixado` e gera multa no valor exato do teto da categoria (Aluno: R$ 30,00; Professor: R$ 50,00; Visitante: R$ 20,00).

---

## 🚀 Endpoints da API

### Usuários
- `POST /usuarios`: Cadastra usuário (`201 Created`, validação de e-mail e matrícula únicos).
- `GET /usuarios`: Lista usuários (filtros por `categoria` e `situacao`).
- `GET /usuarios/{id}`: Detalhes do usuário (`404` se não existir).
- `PUT /usuarios/{id}` e `PATCH /usuarios/{id}`: Atualiza dados cadastrais.
- `DELETE /usuarios/{id}`: Remove usuário (`204 No Content`; bloqueado se houver empréstimos ativos ou multas em aberto).

### Livros
- `POST /livros`: Cadastra livro (`201 Created`, ISBN único).
- `GET /livros`: Lista livros (filtros por `area` e `autor`).
- `GET /livros/{id}`: Detalhes do livro.
- `PUT /livros/{id}` e `PATCH /livros/{id}`: Atualiza dados do livro.
- `DELETE /livros/{id}`: Remove livro (`400` se houver exemplares emprestados).

### Exemplares
- `POST /exemplares`: Cadastra exemplar com código de tombo único (`201 Created`).
- `GET /exemplares`: Lista exemplares (filtros por `livro_id` e `estado`).
- `GET /exemplares/{id}`: Detalhes do exemplar.
- `PUT /exemplares/{id}` e `PATCH /exemplares/{id}`: Atualiza estado (`disponivel`, `em_reparo`, `baixado`, etc.).
- `DELETE /exemplares/{id}`: Remove exemplar (`400` se estiver emprestado).

### Empréstimos
- `POST /emprestimos`: Cria empréstimo (`201 Created`, valida regras 1 e 6).
- `POST /emprestimos/{id}/renovar`: Renova empréstimo (`200 OK`, valida regra 3).
- `POST /emprestimos/{id}/devolver`: Registra devolução (`200 OK`, executa regras 4, 5 e 7).
- `GET /emprestimos/usuario/{usuario_id}`: Lista empréstimos de um usuário.
- `GET /emprestimos`: Lista geral de empréstimos com filtros.
- `GET /emprestimos/{id}`: Detalhes de um empréstimo.

### Reservas
- `POST /reservas`: Cria reserva na fila (`201 Created`).
- `POST /reservas/{id}/cancelar` ou `DELETE /reservas/{id}`: Cancela reserva e avança a fila (`200 OK`).
- `GET /reservas/livro/{livro_id}`: Lista a fila ativa de um livro ordenada pela posição.
- `GET /reservas`: Lista todas as reservas.
- `POST /reservas/processar-expiradas`: Processa reservas expiradas que ultrapassaram a janela de 48h.

### Multas
- `GET /multas/usuario/{usuario_id}`: Lista todas as multas de um usuário.
- `POST /multas/{id}/pagar`: Registra pagamento da multa aberta (`200 OK`).
- `GET /multas`: Lista geral de multas.
- `GET /multas/{id}`: Detalhes da multa.

### Relatórios
- `GET /relatorios/livros-mais-emprestados?data_inicio=...&data_fim=...&limite=10`: Livros com maior volume de empréstimos no período.
- `GET /relatorios/usuarios-mais-atrasos?limite=10`: Usuários com mais ocorrências de atraso e somatório de dias em atraso.
- `GET /relatorios/taxa-ocupacao-acervo`: Percentual de ocupação do acervo (% de exemplares emprestados) agrupado por área de conhecimento.

---

## 🧪 Como Executar os Testes

Execute a suíte completa de testes automatizados com o pytest:

```bash
pytest -v
```

Todos os 34 testes unitários e de integração cobrem exaustivamente cada regra de negócio, limites numéricos e códigos HTTP.

---

## 🏃 Como Executar a Aplicação

### 1. Instalar dependências (caso necessário):
```bash
pip install -r requirements.txt
```

### 2. Iniciar o servidor:
```bash
python run.py
```
ou via Uvicorn diretamente:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Documentação Interativa:
- **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
