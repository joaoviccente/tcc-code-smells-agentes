# API de Matrículas Acadêmicas

FastAPI + SQLAlchemy 2 + banco relacional (SQLite por padrão; qualquer banco via `DATABASE_URL`).

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload          # docs interativas em http://localhost:8000/docs
python -m pytest -q                     # testes das regras de negócio
```

## Estrutura
| Arquivo | Conteúdo |
|---|---|
| `app/config.py` | Parâmetros numéricos por categoria (28/16/8 créditos, 2/1/0 trancamentos, 15/30/7 dias, prioridade média/alta/baixa) e constantes globais (48h, 3 reprovações, 5 confirmadas, 3 trancamentos) |
| `app/models.py` | Aluno, Disciplina, PreRequisito, Turma (+ HorarioTurma), Matricula, Historico |
| `app/services.py` | Todas as regras de negócio |
| `app/routers/` | Endpoints |

## Endpoints
| Método | Rota | Descrição |
|---|---|---|
| POST/GET | `/alunos` | Criar / listar (filtros `categoria`, `situacao`) |
| GET/PATCH/DELETE | `/alunos/{id}` | Consultar / alterar / remover |
| GET | `/alunos/{id}/matriculas` | Matrículas do aluno (filtros `semestre`, `estado`) |
| GET/POST | `/alunos/{id}/historico` | Consultar histórico / lançar resultado final |
| POST/GET | `/disciplinas` | CRUD de disciplinas (aceita `pre_requisitos: [ids]`) |
| GET/PATCH/DELETE | `/disciplinas/{id}` | |
| POST/DELETE | `/disciplinas/{id}/pre-requisitos[/{req_id}]` | Gerenciar pré-requisitos (impede ciclos) |
| POST/GET | `/turmas` | CRUD de turmas |
| GET/PATCH/DELETE | `/turmas/{id}` | |
| POST | `/turmas/{id}/cancelar`, `/turmas/{id}/encerrar` | Mudanças de estado da turma |
| GET | `/turmas/{id}/lista-espera` | Fila ordenada |
| POST | `/matriculas` | Solicitar |
| GET | `/matriculas/{id}` | Consultar |
| POST | `/matriculas/{id}/confirmar` \| `cancelar` \| `trancar` | Transições |
| POST | `/semestres/{semestre}/encerrar-periodo-matricula` | Aplica a regra 5 |
| POST | `/admin/processar-prazos` | Força expiração das ofertas de 48h |
| GET | `/relatorios/disciplinas-mais-procuradas?semestre=` | |
| GET | `/relatorios/taxa-reprovacao[?semestre=]` | |
| GET | `/relatorios/ocupacao-turmas[?semestre=&departamento=]` | Agrupado por departamento |

Formato do semestre: `AAAA.S` (ex.: `2026.2`). Horário da turma: lista de `{dia_semana: SEG..DOM, hora_inicio, hora_fim}`.

## Decisões de interpretação
- **Fluxo**: `solicitar` → `solicitada` (ocupa vaga) → `confirmar` → `confirmada`. Se a turma estiver lotada, a matrícula é criada como `lista_de_espera`.
- **Vaga liberada (regra 2)**: o primeiro da fila passa a `solicitada` com `prazo_confirmacao = agora + 48h` (vaga reservada). Os prazos vencidos são processados automaticamente a cada operação. Se vários prazos vencem em sequência, cada nova oferta começa no instante em que a anterior expirou.
- **Créditos (regra 1)**: contam as matrículas `solicitada` e `confirmada` do semestre. O limite é verificado de novo na confirmação, o que cobre quem saiu da fila.
- **Prazo de cancelamento/trancamento (regra 4)**: contado a partir da data de confirmação. Trancamento fora do prazo ou acima do limite → 422. Cancelamento de matrícula confirmada fora do prazo → aceito, mas registra no histórico `reprovado` com nota 0 ("reprovação por falta"); esse registro também conta para a regra 3.
- **Contagem de trancamentos**: feita pelos registros `trancado` do histórico (por disciplina na regra 4; por semestre na regra 7).
- **Regra 5**: disparada pelo endpoint de encerramento do período do semestre. Todas as matrículas das turmas canceladas vão para `cancelada`.
- **Regra 6**: o conflito é verificado contra as turmas **confirmadas** do mesmo semestre, tanto na solicitação quanto na confirmação. Horários adjacentes (08–10 e 10–12) não conflitam.
- **Regra 7**: ao 3º trancamento no semestre, o aluno passa a `trancado` e as suas matrículas confirmadas são canceladas. As vagas liberadas vão para a fila.

## Códigos HTTP
`201` criação · `200` sucesso · `204` remoção · `404` recurso inexistente · `422` entrada inválida ou regra violada (pré-requisito, créditos, prazo/limite de trancamento, ciclo de pré-requisitos) · `403` aluno não ativo ou impedido por 3 reprovações · `409` conflito de estado (horário, duplicidade, turma cancelada/encerrada, confirmar estando na lista de espera, transição inválida, remoção com vínculos).

Os erros de negócio retornam `{"erro": "<codigo>", "mensagem": "...", "detalhes": {...}}`.
