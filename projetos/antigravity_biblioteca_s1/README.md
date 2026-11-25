# API REST para Gestão de Biblioteca Universitária

API REST completa desenvolvida em Python (FastAPI + SQLAlchemy + Pydantic) para gerenciamento de uma biblioteca universitária, respeitando integralmente todas as entidades, regras por categoria e regras de negócio especificadas.

---

## 🛠️ Tecnologias e Arquitetura

- **Python 3.12**
- **FastAPI**: Framework web moderno, assíncrono e de alto desempenho para APIs REST.
- **Pydantic v2**: Validação estrita e tipagem de dados de entrada e saída.
- **SQLAlchemy 2.0**: ORM para persistência relacional (SQLite por padrão, extensível para PostgreSQL/MySQL).
- **Uvicorn**: Servidor ASGI de alta performance.
- **Pytest + TestClient**: Suíte completa de testes automatizados com banco isolado em memória.

---

## 📂 Estrutura do Projeto

```
antigravity_biblioteca_s1/
├── app/
│   ├── __init__.py
│   ├── config.py           # Configurações gerais da aplicação
│   ├── database.py         # Conexão com o banco relacional e sessão SQLAlchemy
│   ├── models.py           # Modelos ORM (Usuario, Livro, Exemplar, Emprestimo, Reserva, Multa)
│   ├── schemas.py          # Schemas Pydantic (validação de entrada e serialização)
│   ├── rules.py            # Constantes e regras por categoria de usuário
│   ├── services.py         # Camada de serviços com todas as regras de negócio
│   ├── main.py             # Instância do FastAPI, lifespan e inclusão de rotas
│   └── routers/
│       ├── __init__.py
│       ├── usuarios.py     # Endpoints de Usuários
│       ├── livros.py       # Endpoints de Livros
│       ├── exemplares.py   # Endpoints de Exemplares
│       ├── emprestimos.py  # Endpoints de Empréstimos (criar, renovar, devolver)
│       ├── reservas.py     # Endpoints de Reservas (criar, cancelar, listar fila)
│       ├── multas.py       # Endpoints de Multas (listar, pagar)
│       └── relatorios.py   # Endpoints de Relatórios gerenciais
├── tests/
│   ├── __init__.py
│   ├── conftest.py         # Fixtures de banco em memória e TestClient
│   ├── test_usuarios.py
│   ├── test_livros_exemplares.py
│   ├── test_emprestimos.py
│   ├── test_regras_negocio.py
│   ├── test_reservas.py
│   ├── test_multas.py
│   ├── test_relatorios.py
│   └── test_edge_cases.py
├── requirements.txt
└── README.md
```

---

## 👥 Regras por Categoria de Usuário

| Categoria | Limite de Exemplares | Prazo de Devolução | Renovação Permitida | Multa / Dia Corrido | Teto da Multa |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Aluno** | 3 exemplares | 7 dias | 2 renovações | R$ 1,00 | R$ 30,00 |
| **Professor** | 8 exemplares | 30 dias | 4 renovações | R$ 0,50 | R$ 50,00 |
| **Visitante** | 1 exemplar | 3 dias | Nenhuma (0) | R$ 2,00 | R$ 20,00 |

---

## ⚖️ Regras de Negócio Implementadas

1. **Permissão de Empréstimo**: Apenas usuários com situação `ativo`, sem multas com estado `aberta`, e que estejam abaixo do limite de exemplares de sua categoria.
2. **Suspensão por Atraso > 15 dias**: Usuário com atraso superior a 15 dias em qualquer empréstimo é automaticamente suspenso (`situacao = suspenso`), e a suspensão dura exatamente o dobro dos dias de atraso (`2 * dias_atraso`).
3. **Restrições de Renovação**: A renovação é negada caso exista fila de reserva para aquele livro (`aguardando` ou `disponivel`), se o empréstimo estiver atrasado, ou se o limite de renovações da categoria do usuário já tiver sido atingido.
4. **Fila de Reservas e Prazos**: As reservas entram em fila por ordem de chegada. Quando um exemplar é devolvido, a primeira reserva da fila passa ao estado `disponivel` e o usuário tem 48 horas para retirá-lo. Esgotado esse prazo, a reserva expira e a vez é passada automaticamente para o próximo da fila.
5. **Cálculo de Multas**: Multa acumulada por dia corrido de atraso, limitada ao teto da respectiva categoria. Para a categoria **Professor**, a multa é automaticamente perdoada (`estado = perdoada`) caso o atraso seja de até 2 dias corridos.
6. **Exemplares em Reparo ou Baixados**: Exemplares com estado `em_reparo` ou `baixado` não podem ser emprestados nem reservados. Se o último exemplar disponível de um livro for baixado, todas as reservas ativas daquele livro são canceladas (`estado = cancelada`).
7. **Atraso Superior a 60 dias**: Devolução de exemplar com mais de 60 dias de atraso marca automaticamente o exemplar como `baixado` e gera multa no valor do teto da categoria.

---

## 🚀 Endpoints da API

### Usuários
- `POST /usuarios`: Cadastrar novo usuário (nome, e-mail único, matrícula única, categoria).
- `GET /usuarios`: Listar usuários (filtros opcionais: `categoria`, `situacao`).
- `GET /usuarios/{id}`: Obter detalhes do usuário.
- `PUT /usuarios/{id}`: Atualizar dados cadastrais do usuário.
- `DELETE /usuarios/{id}`: Remover usuário (bloqueado se houver histórico de empréstimos).
- `GET /usuarios/{id}/emprestimos`: Listar empréstimos do usuário.
- `GET /usuarios/{id}/multas`: Listar multas do usuário.

### Livros
- `POST /livros`: Cadastrar livro (título, autor, ISBN único, ano, área de conhecimento).
- `GET /livros`: Listar livros (filtro opcional: `area_conhecimento`).
- `GET /livros/{id}`: Obter livro por ID.
- `PUT /livros/{id}`: Atualizar livro.
- `DELETE /livros/{id}`: Remover livro.
- `GET /livros/{id}/reservas`: Listar a fila de reservas ativas do livro em ordem de chegada.

### Exemplares
- `POST /exemplares`: Cadastrar exemplar vinculado a um livro (código de tombo único, estado).
- `GET /exemplares`: Listar exemplares (filtros opcionais: `livro_id`, `estado`).
- `GET /exemplares/{id}`: Obter exemplar por ID.
- `PUT /exemplares/{id}`: Atualizar código de tombo ou estado (`disponivel`, `emprestado`, `reservado`, `em_reparo`, `baixado`).
- `DELETE /exemplares/{id}`: Remover exemplar.

### Empréstimos
- `POST /emprestimos`: Criar novo empréstimo (valida Regras 1, 4 e 6).
- `GET /emprestimos`: Listar empréstimos (filtros opcionais: `usuario_id`, `estado`).
- `GET /emprestimos/{id}`: Obter empréstimo por ID.
- `POST /emprestimos/{id}/renovar`: Renovar empréstimo (valida Regra 3).
- `POST /emprestimos/{id}/devolver`: Registrar devolução (calcula multas, suspensões e gerencia fila de reservas conforme Regras 2, 4, 5 e 7).

### Reservas
- `POST /reservas`: Criar reserva para um livro (valida Regras 4 e 6).
- `GET /reservas`: Listar reservas (filtros: `livro_id`, `usuario_id`, `estado`).
- `GET /reservas/{id}`: Obter reserva por ID.
- `POST /reservas/{id}/cancelar`: Cancelar reserva e repassar exemplar ao próximo da fila.
- `DELETE /reservas/{id}`: Alias para cancelar reserva.

### Multas
- `GET /multas`: Listar multas (filtros: `usuario_id`, `estado`).
- `GET /multas/{id}`: Obter detalhes da multa.
- `POST /multas/{id}/pagar`: Registrar pagamento da multa.

### Relatórios
- `GET /relatorios/livros-mais-emprestados`: Ranking dos livros com mais empréstimos no período (parâmetros: `data_inicio`, `data_fim`).
- `GET /relatorios/usuarios-mais-atrasos`: Usuários com maior número de empréstimos em atraso.
- `GET /relatorios/taxa-ocupacao-acervo`: Percentual de ocupação do acervo (exemplares emprestados / total ativos) agrupado por área de conhecimento.

---

## ⚙️ Como Executar

### 1. Instalação das dependências
```bash
pip install -r requirements.txt
```

### 2. Iniciar o servidor
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Acessar a documentação interativa
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🧪 Como Executar os Testes

Execute a suíte de testes com o pytest:
```bash
pytest
```
Para ver a saída detalhada com cobertura de cada teste:
```bash
pytest -v
```
