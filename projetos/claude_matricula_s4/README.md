# API de Matrículas Acadêmicas

FastAPI + SQLAlchemy 2 + SQLite (qualquer banco relacional via `DATABASE_URL`).

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload          # docs em http://localhost:8000/docs
python -m pytest -q                    # 31 testes
# Postgres: DATABASE_URL=postgresql+psycopg://user:senha@host/db uvicorn app.main:app
```

## Estrutura

| Arquivo | Conteúdo |
|---|---|
| `app/models.py` | Entidades: Aluno, Disciplina, PreRequisito, Turma, Matricula, Historico |
| `app/regras.py` | **Todos os parâmetros numéricos** (créditos, trancamentos, prazos, prioridades, 48h, 3 reprovações, 5 confirmadas, 3 trancamentos) |
| `app/servicos.py` | Regras de negócio (solicitar, confirmar, cancelar, trancar, lista de espera, encerramento do período) |
| `app/schemas.py` | Validação de entrada/saída (Pydantic) |
| `app/routers/` | Endpoints |
| `app/clock.py` | Relógio único (permite simular passagem do tempo nos testes) |

## Regras por categoria (`app/regras.py`)

| Categoria | Máx. créditos/semestre | Trancamentos por disciplina | Prazo de cancelamento | Prioridade na espera |
|---|---|---|---|---|
| graduacao | 28 | 2 | 15 dias | média |
| pos | 16 | 1 | 30 dias | alta |
| especial | 8 | 0 | 7 dias | baixa |

## Endpoints

- **Alunos**: `POST/GET /alunos`, `GET/PATCH/DELETE /alunos/{id}`
- **Disciplinas**: `POST/GET /disciplinas`, `GET/PATCH/DELETE /disciplinas/{id}`, pré-requisitos em `GET/POST /disciplinas/{id}/pre-requisitos` e `DELETE /disciplinas/{id}/pre-requisitos/{req_id}`
- **Turmas**: `POST/GET /turmas`, `GET/PATCH/DELETE /turmas/{id}` (o `PATCH` aceita `estado: cancelada|encerrada`)
- **Matrículas**: `POST /matriculas` (solicitar), `POST /matriculas/{id}/confirmar`, `/cancelar`, `/trancar`, `GET /matriculas/{id}`, `GET /alunos/{id}/matriculas?semestre=&estado=`
- **Lista de espera**: `GET /turmas/{id}/lista-espera`, `POST /lista-espera/processar-expiracoes`
- **Histórico**: `GET /alunos/{id}/historico`, `POST /historico` (lança resultado)
- **Período**: `POST /semestres/{semestre}/encerrar-periodo-matricula` (regra 5)
- **Relatórios**: `GET /relatorios/disciplinas-mais-procuradas?semestre=`, `GET /relatorios/taxa-reprovacao[?semestre=]`, `GET /relatorios/ocupacao-turmas?semestre=`

Formato de horário: `[{"dia": "seg", "inicio": "08:00", "fim": "10:00"}]`; semestre: `AAAA.1` ou `AAAA.2`.

## Códigos HTTP

`201` criação · `200` sucesso · `204` remoção · `404` recurso inexistente ·
`409` conflito de estado/unicidade (duplicidade, turma indisponível, matrícula em estado inválido, prazo de 48h expirado, aguardando vaga) ·
`422` dados inválidos **ou** regra de negócio violada. Erros têm o corpo `{"erro": "CODIGO", "mensagem": "...", "detalhes": {...}}`.

## Decisões de interpretação

- **Ocupação de vagas**: matrículas `solicitada` e `confirmada` ocupam vaga; uma vaga oferecida a alguém da lista de espera fica reservada durante as 48h.
- **Limite de créditos**: soma as matrículas `solicitada`, `confirmada` e `lista_de_espera` do semestre, para que ninguém ultrapasse o limite ao sair da lista de espera.
- **Lista de espera (48h)**: a vaga oferecida continua com estado `lista_de_espera`, agora com `prazo_confirmacao` preenchido. As expirações são processadas sempre que a turma é acessada e também por `POST /lista-espera/processar-expiracoes` (que pode ser agendado num cron). O prazo do próximo da fila conta a partir do momento em que a vaga foi liberada, não do momento em que o processamento rodou.
- **Prazo de cancelamento/trancamento**: conta a partir da confirmação da matrícula. Trancar fora do prazo é recusado (`422`). **Cancelar** fora do prazo é permitido, mas registra `reprovado` no histórico com nota 0 e a observação "reprovado por falta". Cancelar matrículas não confirmadas nunca gera penalidade.
- **Limite de trancamentos por disciplina**: conta os registros `trancado` no histórico daquele aluno naquela disciplina, somando todos os semestres.
- **Regra 7**: conta as matrículas `trancada` do aluno no semestre. Ao atingir 3, o aluno passa a `trancado` e todas as suas matrículas `confirmada` são canceladas, e as vagas liberadas vão para a lista de espera.
- **Regra 5**: é executada explicitamente pelo endpoint de encerramento do período. Quando a turma é cancelada, todas as suas matrículas que ainda não estavam canceladas passam a `cancelada`.
- **Regra 6**: conflito existe quando há sobreposição no mesmo dia com uma turma confirmada do mesmo semestre. Horários que apenas se encostam (10:00 e 10:00) não conflitam. A verificação é feita na solicitação e repetida na confirmação.
- Também é bloqueada mais de uma matrícula ativa na mesma disciplina no mesmo semestre (`409`).
