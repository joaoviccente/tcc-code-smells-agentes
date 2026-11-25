# API de matriculas academicas

Requer Python 3.11 ou posterior. Execute na raiz do projeto.

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app:app
```

A documentacao interativa fica em http://127.0.0.1:8000/docs. O SQLite cria
`matriculas.sqlite3` na primeira inicializacao. A variavel de ambiente
`MATRICULAS_DB` permite escolher outro arquivo de banco.

## Rotas

| Operacao | Metodo e rota |
| --- | --- |
| Cadastrar e listar alunos, disciplinas e turmas | `POST`, `GET` em `/alunos`, `/disciplinas` e `/turmas` |
| Consultar, substituir e excluir um registro | `GET`, `PUT`, `DELETE` em `/{recurso}/{id}` |
| Solicitar matricula | `POST /matriculas` com `aluno_id` e `turma_id` |
| Confirmar uma oferta, cancelar ou trancar | `POST /matriculas/{id}/confirmar`, `/cancelar` ou `/trancar` |
| Listar matriculas de um aluno | `GET /alunos/{id}/matriculas` |
| Consultar ofertas e fila de uma turma | `GET /turmas/{id}/lista-de-espera` |
| Listar e cadastrar pre-requisitos | `GET`, `POST /disciplinas/{id}/pre-requisitos` |
| Remover pre-requisito | `DELETE /disciplinas/{id}/pre-requisitos/{exigida_id}` |
| Consultar e registrar resultados academicos | `GET`, `POST /alunos/{id}/historico` |
| Encerrar o periodo de matricula | `POST /periodos-matricula/{semestre}/encerrar` |
| Consultar demanda | `GET /relatorios/disciplinas-mais-procuradas?semestre=2026-1` |
| Consultar taxa de reprovacao e ocupacao | `GET /relatorios/taxa-reprovacao` e `GET /relatorios/ocupacao`, com filtro opcional `semestre` |

O semestre usa o formato `AAAA-1` ou `AAAA-2`. O horario e uma lista de
intervalos semanais. Cada intervalo tem `dia` de 1 (segunda-feira) a 7
(domingo) e campos `inicio` e `fim` em formato `HH:MM`, no horario local
da universidade. A nota do historico, quando informada, vai de 0 a 10.

Com vaga livre, a solicitacao retorna uma matricula confirmada. Com a
turma lotada, retorna uma matricula em lista de espera. Quando uma vaga
e liberada, a oferta corresponde a uma matricula `solicitada` com
`prazo_confirmacao` de 48 horas. Uma oferta reserva a vaga enquanto
estiver vigente. A API atualiza vencimentos em segundo plano e antes
de processar consultas e alteracoes. Datas de matricula e oferta usam UTC.

O prazo de cancelamento e trancamento conta a partir da confirmacao,
incluindo o instante em que se completam os dias da categoria. A
operacao de encerramento e executada pela universidade ao fim do
periodo. Turmas com pelo menos cinco confirmacoes passam a `encerrada`
e preservam as matriculas confirmadas. Turmas abaixo desse minimo
passam a `cancelada` e todas as matriculas sao canceladas.

O relatorio de demanda conta todas as solicitacoes registradas. A taxa
de reprovacao divide as reprovacoes pelo total de aprovacoes e
reprovacoes e retorna `null` sem resultados. A ocupacao divide as
confirmacoes pelo total de vagas nas turmas do departamento, com
exclusao das turmas canceladas.

Criacoes retornam 201 e exclusoes retornam 204. Registros inexistentes
retornam 404, conflitos de estado ou regras academicas retornam 409 e
entradas invalidas retornam 422.
