# API de matrículas acadêmicas

Requer Python 3.11 ou superior. O SQLite cria o banco automaticamente na primeira inicialização. Defina a variável de ambiente `MATRICULAS_DB` para usar outro arquivo.

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app
```

Abra `http://127.0.0.1:8000/docs` para consultar os esquemas e experimentar os endpoints.

| Método | Rota | Operação |
| --- | --- | --- |
| GET, POST | `/alunos`, `/disciplinas`, `/turmas` | Listar e criar registros |
| GET, PUT, DELETE | `/alunos/{id}`, `/disciplinas/{id}`, `/turmas/{id}` | Consultar, substituir ou excluir um registro |
| GET, POST | `/disciplinas/{id}/pre-requisitos` | Consultar ou adicionar um requisito com `{"exigida_id": 1}` |
| DELETE | `/disciplinas/{id}/pre-requisitos/{exigida_id}` | Remover um requisito |
| POST | `/matriculas` | Solicitar com `{"aluno_id": 1, "turma_id": 1}` |
| POST | `/matriculas/{id}/confirmar`, `/matriculas/{id}/cancelar`, `/matriculas/{id}/trancar` | Operar sobre uma matrícula |
| GET | `/alunos/{id}/matriculas` | Listar as matrículas do aluno |
| GET | `/turmas/{id}/lista-de-espera` | Consultar ofertas vigentes e fila ordenada |
| GET, POST | `/alunos/{id}/historico` | Consultar ou registrar um resultado acadêmico |
| POST | `/periodos-matricula/{semestre}/encerrar` | Encerrar novas solicitações e cancelar turmas com menos de cinco confirmações |
| GET | `/relatorios/disciplinas-mais-procuradas?semestre=2026.1` | Contar todas as solicitações registradas no semestre |
| GET | `/relatorios/taxa-reprovacao` | Dividir reprovações pelo total de aprovações e reprovações |
| GET | `/relatorios/ocupacao-turmas` | Dividir confirmações pelo total de vagas das turmas não canceladas, por departamento |

Os dois últimos relatórios aceitam o filtro opcional `semestre`.

Use semestres no formato `AAAA.1` ou `AAAA.2`. Cada turma tem um intervalo semanal. Os dias vão de 1 (segunda-feira) a 7 (domingo). Exemplo de horário: `{"dia": 1, "inicio": "08:00", "fim": "10:00"}`.

Uma solicitação com vaga disponível é confirmada imediatamente. Uma vaga oferecida pela fila fica reservada por 48 horas e aparece como `solicitada` até a confirmação ou expiração. A API verifica ofertas vencidas ao processar requisições e a cada 30 segundos enquanto está em execução. As datas são armazenadas em UTC. O prazo de cancelamento e trancamento começa na confirmação da matrícula. Após o encerramento do período, as turmas que atingiram o mínimo continuam processando suas filas existentes.

As operações de criação retornam HTTP 201. Exclusões retornam 204, referências inexistentes retornam 404, conflitos com as regras de negócio retornam 409 e entradas inválidas retornam 422.

## Testes

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest -v
```
