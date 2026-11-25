# API de Gestão de Matrículas Acadêmicas

API REST desenvolvida em Python (FastAPI + SQLAlchemy) para gestão de matrículas acadêmicas de uma universidade, com suporte a persistência relacional, validação rigorosa de dados de entrada e implementação integral de todas as regras de negócio e limites por categoria de aluno.

---

## 🏛️ Entidades e Atributos

- **Aluno**:
  - `id`: Identificador único (chave primária)
  - `matricula`: Código de matrícula único (ex: `"20261001"`)
  - `nome`: Nome completo do aluno
  - `email`: Endereço de e-mail institucional único
  - `categoria`: `graduacao`, `pos` ou `especial`
  - `situacao`: `ativo`, `trancado` ou `jubilado`

- **Disciplina**:
  - `id`: Identificador único (chave primária)
  - `codigo`: Código único (ex: `"MAT001"`, `"DCC001"`)
  - `nome`: Nome da disciplina
  - `numero_creditos`: Quantidade de créditos acadêmicos
  - `carga_horaria`: Carga horária total em horas
  - `departamento`: Departamento responsável (ex: `"Matemática"`, `"Ciência da Computação"`)
  - `pre_requisitos`: Lista de disciplinas obrigatórias previamente cumpridas

- **Turma**:
  - `id`: Identificador único
  - `disciplina_id`: Referência à disciplina
  - `semestre`: Período letivo (ex: `"2026.1"`)
  - `professor`: Nome do docente responsável
  - `numero_vagas`: Capacidade máxima de vagas ofertadas
  - `horario`: Dias e horários (ex: `"SEG 08:00-10:00, QUA 08:00-10:00"`)
  - `estado`: `aberta`, `lotada`, `cancelada` ou `encerrada`

- **Matrícula**:
  - `id`: Identificador único
  - `aluno_id`: Referência ao aluno
  - `turma_id`: Referência à turma
  - `data`: Data e hora da solicitação
  - `estado`: `solicitada`, `confirmada`, `lista_de_espera`, `cancelada` ou `trancada`
  - `data_limite_confirmacao`: Prazo limite para confirmação (quando promovido da fila)

- **Pré-Requisito**:
  - Tabela associativa que vincula uma disciplina a outra exigida como requisito prévio.

- **Histórico**:
  - `id`: Identificador único
  - `aluno_id`: Referência ao aluno
  - `disciplina_id`: Referência à disciplina
  - `semestre`: Semestre em que a disciplina foi cursada
  - `nota`: Nota obtida (0.0 a 10.0)
  - `situacao`: `aprovado`, `reprovado`, `trancado` ou `reprovado_por_falta`
  - `observacao`: Detalhes adicionais (ex: reprovação decorrente de cancelamento fora do prazo)

---

## 📋 Regras por Categoria de Aluno

| Categoria | Máximo de Créditos / Semestre | Limite de Trancamentos / Disciplina | Prazo de Cancelamento | Prioridade na Lista de Espera |
|---|:---:|:---:|:---:|:---:|
| **Graduação** | 28 créditos | Até 2 trancamentos | 15 dias | Média (2) |
| **Pós** | 16 créditos | 1 trancamento | 30 dias | Alta (3) |
| **Especial** | 8 créditos | Nenhum trancamento (0) | 7 dias | Baixa (1) |

---

## ⚙️ Regras de Negócio Implementadas

1. **Permissão de Matrícula**:
   - Apenas alunos com situação `ativo` podem se matricular.
   - O aluno deve ter sido previamente aprovado em todos os pré-requisitos da disciplina no histórico escolar.
   - O total de créditos acumulados no semestre (disciplinas já confirmadas + nova disciplina) não pode exceder o teto da sua categoria.

2. **Lista de Espera e Promoção (48 Horas)**:
   - Se a turma atingir sua capacidade de vagas, novas solicitações entram na `lista_de_espera`.
   - A fila é ordenada decrescentemente pela prioridade da categoria (`pos` > `graduacao` > `especial`) e, em caso de empate, pela data da solicitação (mais antiga primeiro).
   - Quando uma vaga é liberada (por cancelamento ou trancamento), o primeiro da fila é promovido ao estado `solicitada` e tem exatamente **48 horas** para confirmar.
   - Caso o prazo de 48h expire sem confirmação, a matrícula é cancelada e a vaga é automaticamente repassada ao próximo candidato da fila.

3. **Impedimento por Reprovações Recorrentes**:
   - Aluno reprovado 3 vezes na mesma disciplina fica expressamente impedido de efetuar nova matrícula nela.

4. **Trancamento vs. Cancelamento**:
   - O trancamento só é permitido se solicitado dentro do prazo de cancelamento da respectiva categoria e respeitando o número máximo de trancamentos da categoria para aquela disciplina.
   - Caso o cancelamento ocorra fora do prazo da categoria, a matrícula é cancelada e registra automaticamente uma `reprovacao_por_falta` no histórico acadêmico do aluno.

5. **Cancelamento de Turmas com Baixa Procura**:
   - Turma com menos de 5 matrículas confirmadas ao encerramento do período de matrícula é cancelada, e todas as suas matrículas passam ao estado `cancelada`.

6. **Conflito de Horários**:
   - A matrícula é negada (`HTTP 409 Conflict`) se houver qualquer sobreposição de dias e intervalos de horários com outra turma já confirmada do aluno no mesmo semestre.

7. **Trancamento Cumulativo no Semestre**:
   - Se o aluno acumular 3 trancamentos no mesmo semestre, sua situação institucional passa imediatamente para `trancado` e todas as suas demais matrículas confirmadas no semestre são canceladas, liberando suas vagas para as filas de espera.

---

## 🚀 Endpoints da API

### Alunos (`/alunos`)
- `POST /alunos` - Cadastrar novo aluno (`201 Created`)
- `GET /alunos` - Listar alunos (filtros opcionais: `categoria`, `situacao`) (`200 OK`)
- `GET /alunos/{id}` - Obter dados do aluno (`200 OK` / `404 Not Found`)
- `PUT /alunos/{id}` - Atualizar dados do aluno (`200 OK` / `404 Not Found`)
- `DELETE /alunos/{id}` - Remover aluno (`204 No Content` / `404 Not Found`)
- `GET /alunos/{id}/matriculas` - Listar matrículas do aluno (`200 OK`)
- `GET /alunos/{id}/historico` - Consultar histórico escolar completo do aluno (`200 OK`)

### Disciplinas (`/disciplinas`)
- `POST /disciplinas` - Cadastrar disciplina com pré-requisitos opcionais (`201 Created`)
- `GET /disciplinas` - Listar disciplinas (filtro opcional: `departamento`) (`200 OK`)
- `GET /disciplinas/{id}` - Obter detalhes e pré-requisitos (`200 OK`)
- `PUT /disciplinas/{id}` - Atualizar disciplina (`200 OK`)
- `DELETE /disciplinas/{id}` - Remover disciplina (`204 No Content`)
- `POST /disciplinas/{id}/pre-requisitos/{pre_req_id}` - Vincular pré-requisito (`200 OK`)
- `DELETE /disciplinas/{id}/pre-requisitos/{pre_req_id}` - Desvincular pré-requisito (`200 OK`)

### Turmas (`/turmas`)
- `POST /turmas` - Cadastrar turma (`201 Created`)
- `GET /turmas` - Listar turmas (filtros: `disciplina_id`, `semestre`, `estado`, `departamento`) (`200 OK`)
- `GET /turmas/{id}` - Obter detalhes com vagas disponíveis e ocupadas (`200 OK`)
- `PUT /turmas/{id}` - Atualizar turma (`200 OK`)
- `DELETE /turmas/{id}` - Remover turma (`204 No Content`)
- `GET /turmas/{id}/fila` - Consultar fila de espera da turma com ranking de prioridade (`200 OK`)
- `POST /turmas/{id}/finalizar-periodo-matricula` - Encerra período da turma (Regra 5: < 5 confirmadas cancela a turma) (`200 OK`)
- `POST /turmas/finalizar-periodo-matricula?semestre=...` - Encerra período para todas as turmas do semestre (`200 OK`)

### Matrículas (`/matriculas`)
- `POST /matriculas` - Solicitar matrícula com todas as validações (Regras 1, 2, 3 e 6) (`201 Created`)
- `POST /matriculas/{id}/confirmar` - Confirmar matrícula reservada da lista de espera (dentro das 48h) (`200 OK`)
- `POST /matriculas/{id}/cancelar` - Cancelar matrícula (Regra 4: no prazo ou fora com reprovação por falta) (`200 OK`)
- `POST /matriculas/{id}/trancar` - Trancar disciplina (Regras 4 e 7) (`200 OK`)
- `GET /matriculas` - Listar matrículas com filtros (`aluno_id`, `turma_id`, `estado`) (`200 OK`)
- `GET /matriculas/{id}` - Obter detalhes da matrícula (`200 OK`)
- `POST /matriculas/processar-expiradas` - Processa cancelamentos de vagas reservadas expiradas após 48h (`200 OK`)

### Histórico Acadêmico (`/historico`)
- `POST /historico` - Inserir registro no histórico (`201 Created`)
- `GET /historico` - Listar registros de histórico (filtros: `aluno_id`, `disciplina_id`, `situacao`) (`200 OK`)
- `GET /historico/{id}` - Obter registro específico (`200 OK`)
- `DELETE /historico/{id}` - Excluir registro (`204 No Content`)

### Relatórios (`/relatorios`)
- `GET /relatorios/disciplinas-mais-procuradas?semestre=...` - Ranking das disciplinas mais procuradas no semestre (`200 OK`)
- `GET /relatorios/taxa-reprovacao?departamento=...` - Taxa percentual de reprovação por disciplina no histórico (`200 OK`)
- `GET /relatorios/ocupacao-departamentos?semestre=...` - Taxa de ocupação de vagas agrupada por departamento e detalhada por turma (`200 OK`)

---

## 🛠️ Como Executar o Projeto

### 1. Pré-requisitos
- Python 3.10+ instalado.

### 2. Instalação das Dependências
```bash
pip install -r requirements.txt
```

### 3. Popular o Banco com Dados de Exemplo (Opcional)
```bash
python seed.py
```

### 4. Executar a Aplicação
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- Documentação Interativa Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- Documentação Alternativa ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 5. Executar a Suíte de Testes Automatizados
```bash
pytest -v
```
Todos os 22 testes unitários e de integração cobrem integralmente todas as 7 regras de negócio, os prazos e limites das 3 categorias de aluno e todos os relatórios.
