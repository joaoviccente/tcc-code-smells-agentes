# API de Gestão de Matrículas Acadêmicas

FastAPI + SQLAlchemy 2 + SQLite (ou qualquer banco relacional via `DATABASE_URL`).

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload        # docs interativas em http://localhost:8000/docs
python -m pytest -q                  # testes
```

## Estrutura

| Arquivo | Conteúdo |
|---|---|
| `app/models.py` | Tabelas: Aluno, Disciplina, PreRequisito, Turma (+HorarioTurma), Matricula, Historico, PeriodoMatricula |
| `app/regras.py` | Parâmetros por categoria (créditos, trancamentos, prazos, prioridade) e constantes das regras |
| `app/services/matriculas.py` | Todas as regras de negócio |
| `app/schemas.py` | Validação de entrada/saída |
| `app/routers/` | Endpoints |

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| POST/GET | `/alunos` | Criar / listar (`categoria`, `situacao`, `skip`, `limit`) |
| GET/PATCH/DELETE | `/alunos/{id}` | Detalhar / atualizar / remover |
| GET | `/alunos/{id}/matriculas` | Matrículas do aluno (`semestre`, `estado`) |
| GET/POST | `/alunos/{id}/historico` | Consultar / lançar registro de histórico |
| POST/GET | `/disciplinas` | Criar / listar (`departamento`) |
| GET/PATCH/DELETE | `/disciplinas/{id}` | |
| GET/POST | `/disciplinas/{id}/pre-requisitos` | Listar / adicionar (`{"requisito_id": n}`) |
| DELETE | `/disciplinas/{id}/pre-requisitos/{req_id}` | |
| POST/GET | `/turmas` | Criar / listar (`semestre`, `disciplina_id`, `estado`) |
| GET/PATCH/DELETE | `/turmas/{id}` | |
| POST | `/turmas/{id}/cancelar`, `/turmas/{id}/encerrar` | Mudança administrativa de estado |
| GET | `/turmas/{id}/lista-espera` | Fila ordenada da turma |
| POST | `/matriculas` | Solicitar (`{"aluno_id", "turma_id"}`) |
| GET | `/matriculas/{id}` | |
| POST | `/matriculas/{id}/confirmar` \| `/cancelar` \| `/trancar` | |
| POST | `/periodos/{semestre}/encerrar-matriculas` | Fim do período de matrícula (regra 5) |
| GET | `/relatorios/disciplinas-mais-procuradas?semestre=` | |
| GET | `/relatorios/taxa-reprovacao[?semestre=&departamento=]` | |
| GET | `/relatorios/ocupacao-turmas?semestre=` | Agrupado por departamento |

Formatos: semestre `AAAA.1` ou `AAAA.2`; horário `[{"dia": "SEG", "inicio": "08:00", "fim": "10:00"}]`.

## Códigos HTTP

`201` criação · `200` sucesso · `204` remoção · `404` recurso inexistente · `409` conflito com o
estado atual (duplicidade, transição inválida, período encerrado, recurso em uso) · `422` dados
inválidos **ou** violação de regra de negócio. Erros de domínio vêm como
`{"erro": {"codigo": "LIMITE_CREDITOS_EXCEDIDO", "mensagem": "...", "detalhes": {...}}}`.

## Decisões de interpretação

- **Fluxo**: solicitar → `solicitada` (vaga reservada) → confirmar → `confirmada`. Se a turma está
  lotada, solicitar → `lista_de_espera`.
- **Vagas ocupadas** = solicitadas + confirmadas + ofertas pendentes da lista de espera. A turma
  vira `lotada`/`aberta` automaticamente.
- **Lista de espera**: prioridade pos (alta) > graduação (média) > especial (baixa), empate pela
  data da solicitação. Ao liberar vaga (cancelamento, trancamento, aumento de vagas), o primeiro
  recebe `prazo_confirmacao = agora + 48h`. Ofertas vencidas são processadas a cada requisição
  (cancela e oferta ao próximo); prazo exatamente em 48h ainda é aceito.
- **Créditos**: contam matrículas solicitadas, confirmadas e em lista de espera no semestre, de
  modo que a promoção da fila nunca ultrapasse o limite. Revalidados na confirmação.
- **Conflito de horário** (regra 6): verificado contra turmas *confirmadas* do aluno no mesmo
  semestre, na solicitação e na confirmação. Intervalos que apenas se encostam não conflitam.
- **Prazo de cancelamento/trancamento**: contado a partir da data de confirmação da matrícula.
  Cancelar matrícula confirmada fora do prazo registra `reprovado` com nota 0 ("reprovação por
  falta"), que conta para a regra 3. Cancelar solicitação ou lista de espera não tem prazo.
- **Trancamentos** são registrados no histórico (`trancado`); o limite por disciplina considera
  todos os semestres; a regra 7 conta os trancamentos do semestre. Ao atingir 3, além das
  confirmadas, as matrículas pendentes (solicitadas/lista de espera) também são canceladas, pois o
  aluno deixa de ser ativo; matrículas de turmas já encerradas não são afetadas.
- **Regra 5** é disparada por `POST /periodos/{semestre}/encerrar-matriculas`; depois disso não se
  aceitam novas solicitações no semestre. Todas as matrículas da turma cancelada passam a
  `cancelada`.
- Aluno já aprovado na disciplina não pode se matricular nela novamente; um aluno só pode ter uma
  matrícula ativa por disciplina no semestre.
- Datas armazenadas e retornadas em UTC.
