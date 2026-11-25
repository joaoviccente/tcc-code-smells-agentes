# API de Gestao de Matriculas Academicas

FastAPI + SQLAlchemy 2 + SQLite (qualquer banco relacional via `DATABASE_URL`).

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload        # documentacao interativa em http://localhost:8000/docs
python -m pytest -q                  # 26 testes cobrindo CRUD e as 7 regras
```

`DATABASE_URL` padrao: `sqlite:///./matriculas.db` (ex.: `postgresql+psycopg://user:pw@host/db`). As tabelas sao criadas na inicializacao.

## Estrutura

| Arquivo | Conteudo |
|---|---|
| `app/models.py` | Entidades e enums (Aluno, Disciplina, PreRequisito, Turma, Matricula, Historico) |
| `app/regras.py` | **Todos os parametros numericos** (creditos, trancamentos, prazos, prioridades, 48h, 3 reprovacoes, 5 confirmadas, 3 trancamentos) |
| `app/services.py` | Regras de negocio |
| `app/schemas.py` | Validacao de entrada/saida (Pydantic) |
| `app/routers/` | Endpoints |

## Endpoints

| Metodo | Rota | Descricao |
|---|---|---|
| POST/GET | `/alunos` | Criar / listar (`categoria`, `situacao`) |
| GET/PATCH/DELETE | `/alunos/{id}` | Consultar / alterar / remover |
| GET | `/alunos/{id}/matriculas` | Matriculas do aluno (`semestre`, `estado`) |
| GET/POST | `/alunos/{id}/historico` | Consultar / lancar resultado no historico |
| POST/GET | `/disciplinas` | CRUD de disciplinas (+ `GET/PATCH/DELETE /disciplinas/{id}`) |
| GET/POST | `/disciplinas/{id}/pre-requisitos` | Listar / adicionar pre-requisito (ciclos sao rejeitados) |
| DELETE | `/disciplinas/{id}/pre-requisitos/{requisito_id}` | Remover pre-requisito |
| POST/GET | `/turmas` | CRUD de turmas (+ `GET/PATCH/DELETE /turmas/{id}`) |
| GET | `/turmas/{id}/lista-espera` | Fila ordenada da turma |
| POST | `/matriculas` | Solicitar matricula |
| GET | `/matriculas/{id}` | Consultar (inclui `posicao_fila`) |
| POST | `/matriculas/{id}/confirmar` \| `/cancelar` \| `/trancar` | Transicoes de estado |
| POST | `/semestres/{semestre}/encerrar-periodo-matricula` | Fim do periodo (regra 5) |
| POST | `/lista-espera/processar-expiracoes` | Expira ofertas de 48h em lote (para agendamento) |
| GET | `/relatorios/disciplinas-mais-procuradas?semestre=` | Ranking de solicitacoes |
| GET | `/relatorios/taxa-reprovacao` | Reprovados / (aprovados + reprovados), filtros `semestre`, `departamento` |
| GET | `/relatorios/ocupacao-turmas` | Confirmadas / vagas por departamento e turma |

Formatos: semestre `AAAA.1` ou `AAAA.2`; horario `[{"dia": "seg", "inicio": "08:00", "fim": "10:00"}]` (`seg`..`sab`).

## Codigos HTTP

`201` criacao · `200` sucesso · `204` remocao · `404` recurso inexistente · `409` conflito com o estado atual (duplicidade, estado invalido, turma cancelada, choque de horario, remocao com dependentes) · `422` entrada invalida ou regra de negocio violada (inativo, pre-requisito, creditos, 3 reprovacoes, prazo/limite de trancamento).

## Ciclo da matricula e decisoes de interpretacao

- **Solicitar**: com vaga, vira `solicitada` (ja reserva a vaga); sem vaga, vira `lista_de_espera` e a turma fica `lotada`. **Confirmar** a torna `confirmada`.
- **Creditos (regra 1)**: contam as matriculas `solicitada`, `confirmada` e `lista_de_espera` do semestre, para que uma confirmacao posterior nunca estoure o limite.
- **Lista de espera (regra 2)**: ordem por prioridade (pos > graduacao > especial) e depois data da solicitacao. Quando uma vaga e liberada (cancelamento, trancamento, aumento de vagas), o primeiro recebe `prazo_confirmacao = agora + 48h` e a vaga fica reservada para ele. Expirado o prazo, a matricula e cancelada e a oferta passa ao proximo. A expiracao e verificada automaticamente sempre que a turma/matricula e acessada, e tambem pode ser disparada em lote pelo endpoint de processamento.
- **Prazo de cancelamento (regra 4)**: contado a partir da confirmacao (ou da solicitacao, se nao confirmada) e vale por exatamente 15/30/7 dias (x 24h). Trancamento so de matricula confirmada, dentro do prazo e abaixo do limite por disciplina (contado pelos registros `trancado` no historico); especial nunca pode trancar. Fora do prazo, o trancamento e negado e o **cancelamento** de matricula confirmada lanca `reprovado`, nota 0, "reprovacao por falta". Cancelamento dentro do prazo nao gera registro.
- **Regra 5**: e aplicada ao chamar `POST /semestres/{s}/encerrar-periodo-matricula` (o sistema nao tem calendario academico). Turmas `aberta`/`lotada` com menos de 5 confirmadas sao canceladas e todas as matriculas ativas delas passam a `cancelada`.
- **Regra 6**: o choque de horario e verificado contra as turmas confirmadas do aluno no mesmo semestre, tanto na solicitacao quanto na confirmacao.
- **Regra 7**: ao chegar a 3 matriculas `trancada` no semestre, o aluno passa a `trancado` e todas as suas matriculas ativas (confirmadas e tambem as pendentes) sao canceladas, com as vagas repassadas a lista de espera.
- Estados de turma `aberta`/`lotada` sao calculados; manualmente so e possivel definir `cancelada` (cancela as matriculas) ou `encerrada`.
