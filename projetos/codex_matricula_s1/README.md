# Matrículas acadêmicas

API REST com FastAPI e SQLite. Requer Python 3.11+ e SQLite 3.35+.

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app
```

A documentação interativa fica em `/docs` e o esquema em `/openapi.json`. O banco `matriculas.sqlite3` é criado na inicialização. Use a variável de ambiente `MATRICULAS_DB` para definir outro caminho.

| Recurso | Rotas |
| --- | --- |
| Alunos, disciplinas e turmas | `GET` e `POST` em `/alunos`, `/disciplinas` e `/turmas`. `GET`, `PUT` e `DELETE` em cada recurso por ID |
| Pré-requisitos | `GET/POST /disciplinas/{id}/pre-requisitos`, `DELETE /disciplinas/{id}/pre-requisitos/{exigida}` |
| Matrículas | `POST /matriculas` com `aluno_id` e `turma_id`. `POST /matriculas/{id}/confirmar`, `/cancelar` e `/trancar`. `GET /alunos/{id}/matriculas` |
| Fila | `GET /turmas/{id}/lista-de-espera` |
| Histórico | `GET/POST /alunos/{id}/historico`. O POST permite registrar resultados acadêmicos e importar ocorrências anteriores |
| Fim do período | `POST /semestres/{semestre}/encerrar-matriculas` |
| Relatórios | `GET /relatorios/disciplinas-mais-procuradas?semestre=2026-1`, `/relatorios/taxa-reprovacao` e `/relatorios/ocupacao-turmas`. Os dois últimos aceitam `semestre` opcional. Ocupação também aceita `departamento` |

Uma turma usa semestre no formato `AAAA-1` ou `AAAA-2`. O campo `horario` recebe intervalos semanais, por exemplo `[{"dia":"seg","inicio":"08:00","fim":"10:00"}]`. Intervalos contíguos são permitidos.

Solicitações com vaga são confirmadas imediatamente. As demais entram na fila. Uma oferta reserva a vaga por 48 horas e aparece no campo `oferta_expira_em`. O processamento roda durante a execução do servidor e ocorre também antes das operações de matrícula e de consulta da fila. Créditos e conflitos de horário são verificados novamente na confirmação de ofertas.

Os prazos de cancelamento e trancamento contam da confirmação da matrícula. Um trancamento fora do prazo é recusado. O cancelamento de matrícula confirmada depois do prazo registra reprovação com motivo `falta`.

A universidade aciona o encerramento do período pelo endpoint do semestre. Após o encerramento, novas solicitações são bloqueadas. As turmas com cinco ou mais confirmações preservam as vagas e a fila existentes.

O relatório de procura conta cada solicitação persistida. As taxas são frações de 0 a 1. A taxa de reprovação usa como base aprovações e reprovações e retorna `null` na ausência de avaliações. A taxa de ocupação usa confirmações divididas pelo total de vagas de cada turma.

Criações retornam 201 e exclusões, 204. Registros ausentes retornam 404, conflitos com o estado dos recursos retornam 409 e entradas inválidas retornam 422. A API não inclui autenticação.

## Verificação

```powershell
python -m pip install httpx
python verificar.py
```

O script usa um banco temporário e um relógio controlado para exercitar os fluxos HTTP, os limites de prazo e duas solicitações concorrentes para a última vaga.
