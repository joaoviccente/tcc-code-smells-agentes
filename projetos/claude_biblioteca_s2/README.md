# API REST - Biblioteca Universitaria

FastAPI + SQLAlchemy 2 + SQLite (qualquer banco relacional suportado pelo SQLAlchemy
pode ser usado via variavel `DATABASE_URL`, ex.: `postgresql+psycopg://user:senha@host/db`).

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload        # documentacao interativa em http://localhost:8000/docs
python -m pytest -q                  # testes automatizados
```

## Estrutura

| Arquivo | Conteudo |
|---|---|
| `app/regras.py` | Parametros numericos por categoria e das regras de negocio |
| `app/servicos.py` | Toda a logica de negocio (emprestimo, renovacao, devolucao, fila, multas, suspensao) |
| `app/models.py` | Modelo relacional (SQLAlchemy) |
| `app/schemas.py` | Validacao de entrada/saida (Pydantic) |
| `app/routers/` | Endpoints |
| `tests/` | Testes de cada regra, com relogio controlado |

## Endpoints

| Metodo | Rota | Descricao |
|---|---|---|
| POST/GET | `/usuarios` | Cria / lista (filtros `categoria`, `situacao`) |
| GET/PUT/PATCH/DELETE | `/usuarios/{id}` | CRUD |
| GET | `/usuarios/{id}/emprestimos` | Emprestimos do usuario (filtro `estado`) |
| GET | `/usuarios/{id}/multas` | Multas do usuario (filtro `estado`) |
| POST/GET | `/livros` | Cria / lista (filtros `titulo`, `autor`, `area_conhecimento`) |
| GET/PUT/PATCH/DELETE | `/livros/{id}` | CRUD |
| GET | `/livros/{id}/exemplares` | Exemplares do livro |
| GET | `/livros/{id}/reservas` | Fila de reservas (`?historico=true` inclui encerradas) |
| POST/GET | `/exemplares` | Cria / lista (filtros `livro_id`, `estado`) |
| GET/PUT/PATCH/DELETE | `/exemplares/{id}` | CRUD (estado manual: `disponivel`, `em_reparo`, `baixado`) |
| POST | `/emprestimos` | `{usuario_id, exemplar_id}` |
| GET | `/emprestimos/{id}` | Detalhe (inclui dias de atraso e multa) |
| POST | `/emprestimos/{id}/renovacao` | Renova |
| POST | `/emprestimos/{id}/devolucao` | Devolve |
| POST | `/reservas` | `{usuario_id, livro_id}` |
| GET | `/reservas/{id}` | Detalhe |
| POST | `/reservas/{id}/cancelamento` | Cancela (tambem `DELETE /reservas/{id}`) |
| GET | `/multas/{id}` | Detalhe |
| POST | `/multas/{id}/pagamento` | Registra pagamento (`{valor}` opcional; se enviado deve ser igual ao da multa) |
| GET | `/relatorios/livros-mais-emprestados?data_inicio=&data_fim=&limite=` | Ranking no periodo |
| GET | `/relatorios/usuarios-mais-atrasos?limite=` | Ranking de atrasos (periodo opcional) |
| GET | `/relatorios/ocupacao-acervo` | Taxa de ocupacao por area |

Listagens aceitam `skip` e `limit` (paginacao).

## Codigos HTTP

`201` criacao · `200` sucesso · `204` remocao · `404` recurso inexistente ·
`409` violacao de regra de negocio ou unicidade (e-mail, matricula, ISBN, tombo) ·
`422` dados de entrada invalidos.

## Decisoes de interpretacao

- **Processamento temporal**: atrasos, acumulo de multa, suspensoes e expiracao de reservas sao
  atualizados no inicio de cada requisicao (`processar_pendencias`), sem agendador externo.
- **Dias de atraso** = dias corridos entre a data prevista e a data da devolucao (ou hoje).
- **Multa** e criada assim que o emprestimo atrasa e acumula diariamente (bloqueando novos
  emprestimos, Regra 1). Seu valor so e definitivo na devolucao; o pagamento so e aceito apos ela.
  Para professor, enquanto o atraso for de ate 2 dias a multa fica `perdoada`.
- **Categoria do emprestimo**: prazo, renovacoes e multa usam a categoria do usuario no momento
  da retirada; o limite de exemplares usa a categoria atual.
- **Renovacao**: nova data prevista = data da renovacao + prazo da categoria.
- **Suspensao (Regra 2)**: dura 2x os dias de atraso contados a partir da devolucao; enquanto o
  exemplar nao e devolvido o usuario permanece suspenso. Ao fim, volta a `ativo` automaticamente.
  Suspensao manual (via PATCH) e por tempo indeterminado ate reativacao manual.
- **Reserva**: so e aceita se nenhum exemplar estiver disponivel e houver ao menos um exemplar em
  circulacao (nao em reparo/baixado). Ao ser retirada, a reserva passa ao estado adicional
  `atendida`. O prazo de 48h do proximo da fila comeca quando a reserva anterior expira.
- **Regra 6**: as reservas sao canceladas quando o livro fica sem nenhum exemplar em circulacao
  (`disponivel`, `emprestado` ou `reservado`). Se um exemplar separado para uma reserva entrar em
  reparo, a reserva volta a aguardar mantendo sua posicao.
- **Regra 7**: devolucao com mais de 60 dias de atraso gera multa igual ao teto da categoria
  (mesmo que o calculo diario fosse menor, como no caso de professor) e baixa o exemplar.
- **Ocupacao do acervo** = exemplares emprestados / exemplares nao baixados da area (em %).
- **Remocao**: usuarios, livros e exemplares com historico de circulacao nao podem ser removidos
  (409); use suspensao ou baixa.
