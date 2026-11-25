# API de matrículas acadêmicas

Requisitos locais — Python 3.11 ou superior e SQLite 3.35 ou superior, disponível no módulo `sqlite3` do Python.

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app
```

A documentação interativa fica em `http://127.0.0.1:8000/docs`. O arquivo SQLite é criado na inicialização. Defina a variável de ambiente `MATRICULAS_DB` para escolher outro caminho para o banco.

| Operação | Método e rota |
| --- | --- |
| Criar e listar alunos, disciplinas ou turmas | `POST` e `GET` em `/alunos`, `/disciplinas` ou `/turmas` |
| Consultar, substituir ou excluir um registro | `GET`, `PUT` ou `DELETE` na rota da coleção com `/{id}` |
| Cadastrar e consultar pré-requisitos | `POST` e `GET /disciplinas/{id}/pre-requisitos` |
| Registrar e consultar resultados acadêmicos | `POST` e `GET /alunos/{id}/historico` |
| Solicitar matrícula | `POST /matriculas` com `aluno_id` e `turma_id` |
| Confirmar, cancelar ou trancar | `POST /matriculas/{id}/confirmar`, `/cancelar` ou `/trancar` |
| Listar matrículas de um aluno | `GET /alunos/{id}/matriculas` |
| Consultar fila e ofertas vigentes | `GET /turmas/{id}/lista-de-espera` |
| Encerrar período de matrícula | `POST /turmas/{id}/encerrar-periodo-matricula` |
| Consultar relatórios | `GET /relatorios/disciplinas-mais-procuradas`, `/relatorios/taxa-reprovacao` e `/relatorios/ocupacao-turmas` |

Use o formato `2026.1` ou `2026.2` para o semestre. O horário da turma é um intervalo semanal local, por exemplo `{"dia_semana":1,"inicio":"08:00","fim":"10:00"}`, com segunda-feira representada por 1 e domingo por 7. Intervalos adjacentes podem ser cursados no mesmo dia.

Uma solicitação com vaga reserva o lugar até confirmação ou cancelamento. Solicitações sem vaga entram na fila. Quando uma vaga é liberada, a oferta da fila reserva o lugar por 48 horas. Os prazos de cancelamento e trancamento começam na confirmação da matrícula. Créditos e conflitos de horário são verificados na solicitação e novamente na confirmação. O estado `lotada` é calculado a partir da capacidade e das vagas confirmadas ou reservadas.

O encerramento do período é acionado por turma. Abaixo de cinco confirmações, a turma e suas matrículas são canceladas. Nas demais turmas, pedidos novos são bloqueados e os pedidos existentes continuam em processamento.

O relatório de procura exige o parâmetro `semestre` e conta todas as solicitações registradas. Nos outros relatórios, o filtro por semestre é opcional. A taxa de reprovação usa a soma de aprovações e reprovações como denominador. A ocupação usa as matrículas confirmadas e a capacidade total das turmas vigentes ou encerradas de cada departamento.

## Testes

```powershell
python -m pip install "httpx>=0.27,<1"
python -m unittest -v
```
