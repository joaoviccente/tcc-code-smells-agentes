# API REST — Biblioteca Universitária

FastAPI + SQLAlchemy 2 + Pydantic 2. Banco relacional SQLite por padrão (`biblioteca.db`);
qualquer banco suportado pelo SQLAlchemy pode ser usado via `DATABASE_URL`.

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload          # documentação interativa em http://localhost:8000/docs
python -m pytest                       # 46 testes cobrindo todas as regras
```

## Estrutura

| Arquivo | Conteúdo |
|---|---|
| `app/regras.py` | Parâmetros por categoria e constantes das regras (fonte única dos valores numéricos) |
| `app/servicos.py` | Regras de negócio |
| `app/models.py` | Entidades/tabelas |
| `app/schemas.py` | Validação de entrada e formato de saída |
| `app/routers/` | Endpoints |
| `app/relogio.py` | Relógio da aplicação (fixável nos testes) |

## Endpoints

| Recurso | Rotas |
|---|---|
| Usuários | `POST/GET /usuarios`, `GET/PUT/PATCH/DELETE /usuarios/{id}`, `GET /usuarios/{id}/emprestimos`, `GET /usuarios/{id}/multas`, `GET /usuarios/{id}/reservas` |
| Livros | `POST/GET /livros`, `GET/PUT/PATCH/DELETE /livros/{id}`, `GET /livros/{id}/exemplares`, `GET /livros/{id}/reservas` (fila) |
| Exemplares | `POST/GET /exemplares`, `GET/PUT/PATCH/DELETE /exemplares/{id}` |
| Empréstimos | `POST/GET /emprestimos`, `GET /emprestimos/{id}`, `POST /emprestimos/{id}/renovacao`, `POST /emprestimos/{id}/devolucao` |
| Reservas | `POST /reservas`, `GET /reservas/{id}`, `POST /reservas/{id}/cancelamento` |
| Multas | `GET /multas/{id}`, `POST /multas/{id}/pagamento` |
| Relatórios | `GET /relatorios/livros-mais-emprestados?inicio=&fim=&limite=`, `GET /relatorios/usuarios-com-mais-atrasos`, `GET /relatorios/ocupacao-por-area` |

Códigos HTTP: `201` criação, `200` sucesso, `204` exclusão, `404` recurso inexistente,
`409` violação de regra de negócio/estado ou duplicidade (e-mail, matrícula, ISBN, tombo),
`422` dados de entrada inválidos.

Valores monetários são armazenados em centavos (inteiros) e expostos como decimal exato em string (`"30.00"`).

## Decisões de interpretação

- **Processamento temporal**: atrasos, acúmulo de multa, suspensões e expiração de reservas são
  aplicados no início de cada requisição (`servicos.sincronizar`), sem necessidade de job agendado.
- **Multa (regra 5)**: é criada `aberta` no primeiro dia de atraso e atualizada diariamente até a
  devolução; por isso já bloqueia novos empréstimos (regra 1). Só pode ser paga após a devolução,
  quando o valor é definitivo. A tolerância de professor (atraso ≤ 2 dias → `perdoada`) é aplicada na devolução.
- **Suspensão (regra 2)**: ocorre assim que o atraso passa de 15 dias, mesmo sem devolução.
  Termina em `data de devolução + 2 × dias de atraso` e o usuário volta a `ativo` automaticamente.
  Suspensão manual (via `PATCH situacao`) é por tempo indeterminado.
- **Renovação**: novo prazo = data da renovação + prazo da categoria.
- **Reservas**: só são aceitas quando não há exemplar disponível e existe ao menos um exemplar que
  possa retornar (emprestado/reservado). Foi adicionado o estado terminal `atendida` (reserva
  convertida em empréstimo). O prazo de 48 h do próximo da fila conta a partir do momento em que a
  expiração anterior é processada.
- **Regra 6**: "último exemplar disponível" = não resta exemplar emprestado, reservado ou disponível
  (exemplares em reparo não contam, pois não podem ser reservados). Se um exemplar separado para uma
  reserva for baixado/enviado a reparo e houver outros exemplares, a reserva volta a `aguardando` na mesma posição.
- **Regra 7**: com atraso > 60 dias a multa é o teto da categoria mesmo quando o cálculo diário
  seria menor (ex.: professor com 61 dias → R$ 50,00, e não R$ 30,50).
- **Ocupação por área**: `emprestados / exemplares não baixados`, em percentual.
- Exclusões são bloqueadas (`409`) quando há histórico; exemplares devem ser baixados.
