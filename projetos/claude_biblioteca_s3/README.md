# API REST – Biblioteca Universitária

FastAPI + SQLAlchemy 2 + SQLite (qualquer banco relacional suportado pelo SQLAlchemy via `DATABASE_URL`).

## Executar

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload          # documentação interativa em http://localhost:8000/docs
python -m pytest -q                     # testes automatizados
```

`DATABASE_URL` (opcional), ex.: `postgresql+psycopg://user:senha@localhost/biblioteca`. Padrão: `sqlite:///./biblioteca.db`.

## Estrutura

| Arquivo | Conteúdo |
|---|---|
| `app/regras.py` | Parâmetros numéricos por categoria e das regras de negócio (valores exatos do enunciado) |
| `app/servicos.py` | Regras de negócio (empréstimo, renovação, devolução, reservas, multas, suspensão) |
| `app/relatorios.py` | Consultas dos relatórios |
| `app/models.py` / `app/schemas.py` | Modelo relacional / validação de entrada e saída |
| `app/routers/` | Endpoints |

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| POST, GET | `/usuarios` | Criar / listar (filtros `categoria`, `situacao`) |
| GET, PUT/PATCH, DELETE | `/usuarios/{id}` | Detalhar / atualizar / remover |
| GET | `/usuarios/{id}/emprestimos` | Empréstimos do usuário |
| GET | `/usuarios/{id}/multas` | Multas do usuário |
| GET | `/usuarios/{id}/reservas` | Reservas do usuário |
| POST, GET | `/livros` | Criar / listar (filtros `area`, `autor`, `titulo`) |
| GET, PUT/PATCH, DELETE | `/livros/{id}` | Detalhar / atualizar / remover |
| GET | `/livros/{id}/exemplares` | Exemplares do livro |
| GET | `/livros/{id}/reservas` | Fila de reservas do livro |
| POST, GET | `/exemplares` | Criar / listar |
| GET, PUT/PATCH, DELETE | `/exemplares/{id}` | Detalhar / atualizar (tombo, estado) / remover |
| POST, GET | `/emprestimos` | Criar / listar (filtros `usuario_id`, `estado`) |
| POST | `/emprestimos/{id}/renovacao` | Renovar |
| POST | `/emprestimos/{id}/devolucao` | Devolver |
| POST, GET | `/reservas` | Criar / listar |
| POST | `/reservas/{id}/cancelamento` (ou `DELETE /reservas/{id}`) | Cancelar |
| GET | `/multas` | Listar (filtros `usuario_id`, `estado`) |
| POST | `/multas/{id}/pagamento` | Registrar pagamento |
| GET | `/relatorios/livros-mais-emprestados?inicio=AAAA-MM-DD&fim=AAAA-MM-DD&limite=10` | Ranking por período (data de retirada) |
| GET | `/relatorios/usuarios-com-mais-atrasos?inicio=&fim=&limite=10` | Ranking de atrasos |
| GET | `/relatorios/ocupacao-por-area` | Taxa de ocupação do acervo por área |

### Códigos HTTP
`201` criação · `200` sucesso · `204` remoção · `404` recurso inexistente · `409` regra de negócio violada / duplicidade
(e-mail, matrícula, ISBN, tombo) / estado incompatível · `422` dados de entrada inválidos.

Multas trazem `valor_centavos` (inteiro) e `valor` (string decimal, ex. `"30.00"`), evitando erros de ponto flutuante.

## Decisões de interpretação

- **Regras temporais** (atraso, multa acumulada, suspensão, expiração de reservas, fim de suspensão) são aplicadas
  automaticamente no início de cada requisição (`servicos.processar_pendencias`), sem depender de agendador.
- **Dias de atraso** = dias corridos entre a data prevista e a devolução (ou hoje, se ainda em aberto).
- **Multa (regra 5)**: criada como `aberta` assim que o empréstimo atrasa e atualizada diariamente até a devolução,
  limitada ao teto. Para professor, enquanto o atraso é ≤ 2 dias a multa não é materializada; se devolver com
  atraso ≤ 2 dias, ela é registrada como `perdoada`. O pagamento só é aceito após a devolução (valor final).
- **Suspensão (regra 2)**: atraso > 15 dias suspende; o fim é `data de referência + 2 × dias de atraso`
  (enquanto o empréstimo segue aberto a data é recalculada; na devolução, fixa em `devolução + 2 × atraso`).
  Ao término, o usuário volta a `ativo` automaticamente. Suspensão manual (via PATCH) não tem prazo e prevalece.
- **Reservas (regra 4)**: só podem ser feitas quando não há exemplar `disponivel` do livro (se houver, faça o
  empréstimo direto). Ao devolver, o exemplar fica `reservado` para o 1º da fila por 48 h; se expirar, a vez passa ao
  próximo a partir do instante da expiração. Reserva convertida em empréstimo vai para o estado adicional
  **`atendida`** (necessário para encerrar o ciclo sem confundir com `cancelada`/`expirada`).
  `posicao` é a posição na fila de espera (reservas `aguardando`); fica nula nos demais estados.
- **Regra 6**: "último exemplar disponível baixado" = não resta exemplar do livro capaz de atender a fila
  (`disponivel`, `emprestado` ou `reservado`). Nesse caso as reservas ativas são canceladas. Também não se aceita
  reserva de livro cujos exemplares estejam todos em reparo/baixados.
- **Regra 7**: devolução com atraso > 60 dias baixa o exemplar e a multa é o teto da categoria (inclusive para
  professor, cujo valor diário não alcançaria o teto em 61 dias).
- **Renovação**: novo prazo conta a partir da data da renovação.
- **Estados de exemplar**: `emprestado`/`reservado` são controlados pelo sistema. Manualmente são permitidas as
  transições `disponivel ↔ em_reparo` e `disponivel/em_reparo → baixado`.
- **Remoções**: usuário/exemplar com histórico e livro com exemplares/reservas não podem ser removidos (409);
  para retirar um exemplar do acervo use o estado `baixado`.
- **Taxa de ocupação** = exemplares emprestados ÷ exemplares do acervo ativo (exclui baixados).
