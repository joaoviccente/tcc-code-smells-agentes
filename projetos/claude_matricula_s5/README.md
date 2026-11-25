# API de Matrículas Acadêmicas

API REST em **FastAPI + SQLAlchemy 2 + Pydantic 2**, com persistência em banco relacional
(SQLite por padrão; qualquer banco suportado pelo SQLAlchemy via `DATABASE_URL`).

## Execução

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload            # http://localhost:8000/docs
# DATABASE_URL=postgresql+psycopg://user:pass@host/db uvicorn app.main:app
python -m pytest -q                      # testes
```

## Estrutura

| Arquivo | Conteúdo |
|---|---|
| `app/regras.py` | **Todos os parâmetros numéricos** (créditos, trancamentos, prazos, prioridades, 48h, 3 reprovações, 5 confirmadas, 3 trancamentos) |
| `app/models.py` | Entidades ORM: Aluno, Disciplina, PreRequisito, Turma, Matricula, Historico |
| `app/schemas.py` | Validação de entrada/saída |
| `app/servicos.py` | Regras de negócio |
| `app/routers/` | Endpoints |

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| POST/GET | `/alunos` | Criar / listar (filtros `categoria`, `situacao`) |
| GET/PUT/PATCH/DELETE | `/alunos/{id}` | CRUD |
| GET | `/alunos/{id}/matriculas` | Matrículas do aluno (filtros `semestre`, `estado`) |
| GET | `/alunos/{id}/historico` | Histórico com resumo |
| POST/GET | `/disciplinas`, GET/PUT/PATCH/DELETE `/disciplinas/{id}` | CRUD |
| GET/POST | `/disciplinas/{id}/pre-requisitos` | Listar / adicionar (bloqueia ciclos) |
| DELETE | `/disciplinas/{id}/pre-requisitos/{requisito_id}` | Remover |
| POST/GET | `/turmas`, GET/PUT/PATCH/DELETE `/turmas/{id}` | CRUD |
| POST | `/turmas/{id}/cancelar`, `/turmas/{id}/encerrar` | Mudança de estado da turma |
| GET | `/turmas/{id}/matriculas` | Matrículas da turma |
| GET | `/turmas/{id}/lista-espera` | Fila ordenada + vagas aguardando confirmação |
| POST | `/matriculas` | Solicitar (vira `lista_de_espera` se a turma estiver lotada) |
| GET | `/matriculas/{id}` | Consultar (inclui `posicao_fila`) |
| POST | `/matriculas/{id}/confirmar` \| `/cancelar` \| `/trancar` | Operações |
| POST | `/historico` | Registrar resultado (aprovado/reprovado/trancado) |
| POST | `/periodos/{semestre}/encerrar-matriculas` | Fim do período de matrícula (regra 5) |
| GET | `/relatorios/disciplinas-mais-procuradas?semestre=` | Ranking de solicitações |
| GET | `/relatorios/taxa-reprovacao` | Por disciplina (filtros `semestre`, `departamento`) |
| GET | `/relatorios/ocupacao-turmas?semestre=` | Ocupação agrupada por departamento |
| POST | `/admin/processar-prazos` | Força a aplicação dos prazos de 48h |

Formato de horário da turma: `[{"dia": "SEG", "inicio": "08:00", "fim": "10:00"}, ...]`.
Semestre: `AAAA.1` ou `AAAA.2`.

## Códigos HTTP

- `201` criação · `200` sucesso · `204` remoção
- `404` recurso inexistente
- `409` conflito de estado: duplicidade, transição inválida, conflito de horário, turma cancelada/encerrada, prazo de 48h expirado, remoção de registro com vínculos
- `422` dados inválidos (validação) ou regra de negócio violada: aluno não ativo, pré-requisito, créditos, 3 reprovações, trancamento não permitido/fora do prazo/acima do limite

Erros de negócio retornam `{"erro": "CODIGO", "mensagem": "...", "detalhes": {...}}`.

## Decisões de interpretação

- **Fluxo**: `solicitada` (ocupa vaga) → `confirmada`. Vagas ocupadas = solicitadas + confirmadas.
- **Créditos** no semestre: somam matrículas solicitadas, confirmadas e em lista de espera, para que
  a promoção da fila nunca ultrapasse o limite.
- **Lista de espera**: prioridade pos (alta) > graduação (média) > especial (baixa); empate pela data
  de solicitação. Ao liberar vaga, o primeiro passa a `solicitada` com `prazo_confirmacao = +48h`.
  Expirado, é cancelado e a vez passa ao próximo, cujo prazo conta **a partir do instante da expiração**.
  Os prazos são aplicados antes de cada requisição (equivalente a um agendador em tempo real).
- **Prazo de cancelamento/trancamento** conta a partir da data de confirmação da matrícula.
  Trancar fora do prazo é negado (422); **cancelar** uma matrícula confirmada fora do prazo é permitido
  e registra reprovação por falta (nota 0, `por_falta=true`) no histórico.
- **Limite de trancamentos por disciplina** é contado no histórico (todos os semestres).
- **Regra 7**: ao atingir 3 trancamentos no semestre, o aluno passa a `trancado` e todas as suas matrículas
  ativas (confirmadas e também solicitadas/lista de espera) são canceladas; vagas liberadas vão para a fila.
- **Regra 5**: é disparada por `POST /periodos/{semestre}/encerrar-matriculas`.
- Reprovações por falta contam para a regra das 3 reprovações. Aluno já aprovado na disciplina, ou com
  matrícula ativa/trancada nela no mesmo semestre, não pode solicitar outra (409).
- Conflito de horário é verificado na solicitação e novamente na confirmação, contra turmas confirmadas
  do mesmo semestre; intervalos que apenas se tocam (10:00–10:00) não conflitam.
