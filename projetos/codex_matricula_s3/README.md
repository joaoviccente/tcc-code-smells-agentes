# API de matrículas acadêmicas

Requer Python 3.10 ou posterior. Execute na raiz do projeto.

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app
```

A documentação interativa está em `http://127.0.0.1:8000/docs`. A API cria o banco SQLite `matriculas.sqlite3` no diretório de execução. Use a variável de ambiente `MATRICULAS_DB` para escolher outro arquivo.

## Rotas

| Método e rota | Operação |
| --- | --- |
| `GET`, `POST /alunos`, `/disciplinas`, `/turmas` | Listar e criar recursos |
| `GET`, `PUT`, `DELETE /{coleção}/{identificador}` | Consultar, substituir e excluir um recurso |
| `POST /matriculas` | Solicitar matrícula com `aluno_id` e `turma_id` |
| `POST /matriculas/{identificador}/confirmar` | Aceitar uma vaga oferecida |
| `POST /matriculas/{identificador}/cancelar` | Cancelar uma matrícula |
| `POST /matriculas/{identificador}/trancar` | Trancar uma matrícula confirmada |
| `GET /alunos/{aluno_id}/matriculas` | Listar as matrículas do aluno |
| `GET /turmas/{turma_id}/lista-de-espera` | Consultar a fila e as ofertas vigentes |
| `GET`, `POST /alunos/{aluno_id}/historico` | Consultar e registrar resultados acadêmicos |
| `GET`, `POST /disciplinas/{disciplina_id}/pre-requisitos` | Listar e registrar pré-requisitos |
| `DELETE /disciplinas/{disciplina_id}/pre-requisitos/{exigida_id}` | Remover um pré-requisito |
| `POST /periodos/{semestre}/encerrar` | Encerrar solicitações do semestre e cancelar turmas abaixo do mínimo |
| `GET /relatorios/disciplinas-mais-procuradas?semestre=2026-1` | Contar todas as solicitações registradas no semestre, inclusive as canceladas |
| `GET /relatorios/taxa-reprovacao` | Dividir reprovações pelo total de aprovados e reprovados, com filtro opcional de semestre |
| `GET /relatorios/ocupacao` | Dividir confirmações pelas vagas de cada turma, com filtros opcionais de semestre e departamento |

O semestre segue o formato `AAAA-1` ou `AAAA-2`. Uma turma recebe um ou mais intervalos semanais em `horario`. O dia vai de 1 (segunda-feira) a 7 (domingo). A nota, quando informada, varia de 0 a 10.

```json
{
  "disciplina_id": 1,
  "semestre": "2026-1",
  "professor": "Ana Lima",
  "vagas": 30,
  "horario": [
    {"dia": 1, "inicio": "08:00", "fim": "10:00"},
    {"dia": 3, "inicio": "08:00", "fim": "10:00"}
  ]
}
```

A solicitação é confirmada imediatamente quando há vaga disponível. A oferta da fila reserva uma vaga por 48 horas. O servidor verifica os vencimentos a cada 30 segundos e antes das operações da API. A confirmação revalida a elegibilidade do aluno.

O prazo de cancelamento e trancamento começa na confirmação da matrícula. Os horários de aula usam a hora local e os registros de matrícula usam UTC. O encerramento do período é acionado pela rota administrativa. Turmas com cinco ou mais confirmações conservam suas filas e podem concluir ofertas após o encerramento das novas solicitações.

A API retorna `201` na criação, `204` na exclusão, `404` para recursos inexistentes, `409` para conflitos de negócio ou integridade e `422` para entradas inválidas.
