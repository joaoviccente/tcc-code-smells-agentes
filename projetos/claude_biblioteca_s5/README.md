# API REST – Biblioteca Universitária

Feita com FastAPI, SQLAlchemy 2 e SQLite (dá para trocar por outro banco relacional usando a variável `DATABASE_URL`).

## Como executar

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload          # documentação interativa em http://localhost:8000/docs
python -m pytest -q                    # 30 testes de integração
```

## Estrutura

| Arquivo | Conteúdo |
|---|---|
| `app/regras.py` | Parâmetros por categoria (limite, prazo, renovações, multa/dia, teto) e limites das regras 2, 4, 5 e 7 |
| `app/models.py` | Tabelas (com CHECK constraints de estados, UNIQUE em e-mail, matrícula, ISBN e tombo) |
| `app/schemas.py` | Validação de entrada (e-mail, ISBN-10/13 com dígito verificador, ano, enums, campos extras proibidos) |
| `app/servicos.py` | Regras de negócio |
| `app/routers/` | Endpoints |
| `app/clock.py` | Relógio central (os testes o usam para simular a passagem do tempo) |

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| POST/GET | `/usuarios` | Criar / listar (filtros `categoria`, `situacao`) |
| GET/PUT/PATCH/DELETE | `/usuarios/{id}` | CRUD |
| GET | `/usuarios/{id}/emprestimos` | Empréstimos do usuário (filtro `estado`) |
| GET | `/usuarios/{id}/multas` | Multas do usuário (filtro `estado`) |
| POST/GET | `/livros` | Criar / listar (filtros `titulo`, `autor`, `area`) |
| GET/PUT/PATCH/DELETE | `/livros/{id}` | CRUD |
| GET | `/livros/{id}/exemplares` | Exemplares do livro |
| GET | `/livros/{id}/reservas` | Fila de reservas (`?incluir_encerradas=true` para o histórico) |
| POST/GET | `/exemplares` | Criar / listar |
| GET/PUT/PATCH/DELETE | `/exemplares/{id}` | CRUD (o estado pode ir para `disponivel`, `em_reparo` ou `baixado`) |
| POST | `/emprestimos` | Criar `{usuario_id, exemplar_id}` |
| GET | `/emprestimos?usuario_id=` | Listar |
| POST | `/emprestimos/{id}/renovacao` | Renovar |
| POST | `/emprestimos/{id}/devolucao` | Devolver (gera a multa, se houver) |
| POST | `/reservas` | Criar `{usuario_id, livro_id}` |
| POST | `/reservas/{id}/cancelamento` | Cancelar |
| POST | `/multas/{id}/pagamento` | Registrar pagamento |
| GET | `/relatorios/livros-mais-emprestados?inicio=&fim=&limite=` | Ranking de um período |
| GET | `/relatorios/usuarios-mais-atrasos?limite=` | Ranking por quantidade de atrasos |
| GET | `/relatorios/ocupacao-acervo` | Taxa de ocupação por área |

**Códigos HTTP:** 201 para criação, 200 para leitura e operações, 204 para remoção, 404 quando o recurso não existe, 422 para dados de entrada inválidos e 409 para conflitos (duplicidade ou regra de negócio violada). As respostas de erro de regra trazem `{"detail": ..., "codigo": ...}`, por exemplo `limite_exemplares`, `multa_aberta`, `fila_reserva`.

## Interpretações adotadas

- **Atraso** = dias corridos entre a data prevista e a data de referência. Os estados que dependem do tempo (empréstimo `atrasado`, suspensão, expiração de reserva, fim da suspensão) são atualizados no início de cada requisição.
- **Regra 2:** com atraso acima de 15 dias (ou seja, a partir do 16º), o usuário é suspenso na hora, mesmo antes de devolver. Na devolução, o fim da suspensão passa a ser *data da devolução + 2 × dias de atraso*. A reativação é automática, a menos que ainda exista outro empréstimo com mais de 15 dias de atraso. Uma suspensão manual (feita pelo CRUD) não é retirada automaticamente.
- **Multa:** é gerada na devolução. Valor = mín(dias × valor diário, teto). Se for de professor com até 2 dias de atraso, já nasce `perdoada`. Na regra 7 (mais de 60 dias), o valor é o teto da categoria.
- **Renovação:** o novo prazo é contado a partir da data da renovação. Qualquer reserva ativa (`aguardando` ou `disponivel`) do livro conta como fila.
- **Reserva:** só é aceita se nenhum exemplar estiver disponível e se o livro tiver ao menos um exemplar utilizável (fora de reparo e não baixado). Não se aceita reserva duplicada nem de quem já está com o livro. Quando o exemplar de uma reserva `disponivel` é retirado, a reserva passa ao estado **`atendida`**. Esse estado terminal não está no enunciado e foi acrescentado para registrar o atendimento sem confundi-lo com expiração ou cancelamento. A `posicao_fila` numera as reservas ativas por ordem de chegada.
- **Regra 6:** quando um exemplar é baixado e o livro fica sem nenhum exemplar `disponivel`, `emprestado` ou `reservado`, todas as reservas ativas são canceladas. Se o exemplar baixado ou enviado para reparo estava guardado para uma reserva, essa reserva volta a `aguardando` e mantém a posição.
- Um exemplar emprestado não pode mudar de estado pelo CRUD (é preciso registrar a devolução antes), e um exemplar baixado não volta ao acervo. Exemplares novos, ou que voltam do reparo, atendem a fila de reservas automaticamente.
- **Ocupação do acervo** = emprestados ÷ exemplares não baixados da área, em %.
