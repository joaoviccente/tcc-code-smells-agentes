# API REST para Gestão de Matrículas Acadêmicas

API REST desenvolvida em Python (FastAPI + SQLAlchemy + Pydantic v2) para gestão completa de matrículas acadêmicas de uma universidade, com suporte a persistência relacional, regras rigorosas por categoria de estudante, lista de espera com priorização e prazo de expiração de 48h, detecção de conflitos de horário e geração de relatórios gerenciais.

---

## 🏛️ Entidades do Sistema

1. **Aluno**
   - `id`: Identificador único (auto-incremento).
   - `nome`: Nome completo.
   - `matricula`: Código de matrícula único.
   - `email`: Endereço de e-mail único.
   - `categoria`: `graduacao`, `pos` ou `especial`.
   - `situacao`: `ativo`, `trancado` ou `jubilado`.

2. **Disciplina**
   - `id`: Identificador único.
   - `codigo`: Código da disciplina (ex: `MAT001`, `DCC101`).
   - `nome`: Nome da disciplina.
   - `numero_creditos`: Quantidade de créditos acadêmicos (> 0).
   - `carga_horaria`: Carga horária total em horas (> 0).
   - `departamento`: Departamento responsável (ex: `MAT`, `DCC`, `FIS`).

3. **PreRequisito**
   - Tabela associativa que liga uma disciplina a outra exigida como pré-requisito antes da matrícula.

4. **Turma**
   - `id`: Identificador único.
   - `disciplina_id`: Referência à disciplina ofertada.
   - `semestre`: Semestre letivo (ex: `2026.1`).
   - `professor`: Nome do docente responsável.
   - `numero_vagas`: Vagas totais oferecidas (>= 0).
   - `horario`: Descrição dos horários (ex: `SEG 08:00-10:00, QUA 08:00-10:00`, `24M12`).
   - `estado`: `aberta`, `lotada`, `cancelada`, `encerrada`.

5. **Matricula**
   - `id`: Identificador único.
   - `aluno_id`: Referência ao aluno.
   - `turma_id`: Referência à turma.
   - `data`: Data e hora da solicitação.
   - `data_limite_confirmacao`: Prazo de 48 horas quando uma vaga é liberada da lista de espera.
   - `estado`: `solicitada`, `confirmada`, `lista_de_espera`, `cancelada`, `trancada`.

6. **Histórico**
   - `id`: Identificador único.
   - `aluno_id`: Referência ao aluno.
   - `disciplina_id`: Referência à disciplina cursada.
   - `semestre`: Semestre cursado.
   - `nota`: Nota obtida (0.0 a 10.0, ou nula para trancamentos).
   - `situacao`: `aprovado`, `reprovado`, `trancado`, `reprovado_por_falta`.

---

## 🎯 Regras por Categoria de Aluno

| Categoria | Máx. Créditos / Semestre | Limite de Trancamentos / Disciplina | Prazo de Cancelamento | Prioridade na Lista de Espera |
| :--- | :---: | :---: | :---: | :---: |
| **Graduação** | 28 | Até 2 trancamentos | 15 dias | Média (2) |
| **Pós** | 16 | 1 trancamento | 30 dias | Alta (1) |
| **Especial** | 8 | Nenhum (0) | 7 dias | Baixa (3) |

---

## ⚖️ Regras de Negócio Implementadas

1. **Condições para Matrícula**:
   - O aluno deve estar com situação `ativo`.
   - O aluno deve ter sido aprovado em todos os pré-requisitos da disciplina segundo o `Historico`.
   - O aluno não pode ultrapassar o limite de créditos de sua categoria no semestre.
2. **Lista de Espera e Vaga Liberada**:
   - Se a turma estiver lotada (`vagas_ocupadas >= numero_vagas`), a matrícula entra em `lista_de_espera`.
   - A fila é ordenada por prioridade da categoria (`Pós` > `Graduação` > `Especial`) e, em caso de empate, pela data da solicitação (mais antiga primeiro).
   - Quando uma vaga é liberada (cancelamento, trancamento ou aumento de vagas), o primeiro da fila passa ao estado `solicitada` e recebe **48 horas** para confirmar. Se o prazo expirar sem confirmação, a matrícula é cancelada e a vez passa ao próximo.
3. **Bloqueio por Reprovações**:
   - Aluno reprovado 3 vezes na mesma disciplina (`reprovado` ou `reprovado_por_falta`) fica impedido de se matricular nela novamente.
4. **Trancamento e Prazos**:
   - O trancamento só é permitido respeitando o limite de trancamentos por disciplina da categoria (Graduação: 2, Pós: 1, Especial: 0) e dentro do prazo de cancelamento (Graduação: 15 dias, Pós: 30 dias, Especial: 7 dias).
   - Fora do prazo, o cancelamento/trancamento registra automaticamente `reprovado_por_falta` no histórico.
5. **Quórum Mínimo de Turma**:
   - Turma com menos de 5 matrículas confirmadas ao fim do período de matrícula é cancelada, e todas as suas matrículas passam ao estado `cancelada`.
6. **Conflito de Horário**:
   - Matrícula em turma cujo horário conflita com outra turma já confirmada do aluno no mesmo semestre é negada.
7. **Limite Semestral de Trancamentos**:
   - Aluno que acumular 3 trancamentos no mesmo semestre passa à situação `trancado`, e todas as suas matrículas confirmadas naquele semestre são automaticamente canceladas (liberando as vagas para as listas de espera).

---

## 🚀 Endpoints da API

### Alunos (`/alunos`)
- `POST /alunos`: Cria um novo aluno (201 Created).
- `GET /alunos`: Lista alunos com filtros (`categoria`, `situacao`, `termo`).
- `GET /alunos/{id}`: Detalhes do aluno.
- `PUT /alunos/{id}`: Atualiza dados do aluno.
- `DELETE /alunos/{id}`: Remove aluno (204 No Content).
- `GET /alunos/{id}/matriculas`: Consulta matrículas do aluno.
- `GET /alunos/{id}/historico`: Consulta histórico do aluno.

### Disciplinas (`/disciplinas`)
- `POST /disciplinas`: Cadastra disciplina.
- `GET /disciplinas`: Lista disciplinas.
- `GET /disciplinas/{id}`: Detalhes da disciplina.
- `PUT /disciplinas/{id}`: Atualiza disciplina.
- `DELETE /disciplinas/{id}`: Remove disciplina (204 No Content).
- `POST /disciplinas/{id}/pre-requisitos`: Adiciona disciplina como pré-requisito.
- `GET /disciplinas/{id}/pre-requisitos`: Lista pré-requisitos exigidos.
- `DELETE /disciplinas/{id}/pre-requisitos/{prereq_id}`: Remove pré-requisito.

### Turmas (`/turmas`)
- `POST /turmas`: Cadastra turma.
- `GET /turmas`: Lista turmas com filtros (`semestre`, `disciplina_id`, `estado`).
- `GET /turmas/{id}`: Detalhes da turma (incluindo vagas ocupadas, livres e total em espera).
- `PUT /turmas/{id}`: Atualiza turma.
- `DELETE /turmas/{id}`: Remove turma (204 No Content).
- `POST /turmas/{id}/finalizar-periodo-matricula`: Executa a Regra 5 (cancela se confirmadas < 5).
- `GET /turmas/{id}/lista-de-espera`: Consulta a fila ordenada de espera da turma.

### Matrículas (`/matriculas`)
- `POST /matriculas/solicitar` (e `POST /matriculas`): Solicita matrícula para aluno em turma.
- `POST /matriculas/{id}/confirmar`: Confirma matrícula (especialmente ao ser promovido da lista de espera com 48h).
- `POST /matriculas/{id}/cancelar`: Cancela matrícula (verifica prazo da categoria; fora do prazo registra reprovação por falta).
- `POST /matriculas/{id}/trancar`: Tranca matrícula respeitando limites e prazos.
- `GET /matriculas/aluno/{aluno_id}`: Lista todas as matrículas de um aluno.
- `GET /matriculas`: Lista matrículas com filtros.
- `GET /matriculas/{id}`: Detalhes de uma matrícula específica.

### Lista de Espera (`/lista-de-espera`)
- `GET /lista-de-espera/{turma_id}`: Consulta a fila de espera da turma (ordem: Pós > Graduação > Especial; desempate por data asc).
- `POST /lista-de-espera/{turma_id}/processar`: Processa expirações de 48h e avança a fila.

### Histórico Acadêmico (`/historico`)
- `POST /historico`: Insere registro de avaliação ou disciplina cursada.
- `GET /historico/aluno/{aluno_id}`: Consulta histórico acadêmico por aluno.
- `GET /historico`: Lista registros do histórico com filtros.
- `GET /historico/{id}`: Consulta registro específico.
- `PUT /historico/{id}`: Atualiza nota ou situação.
- `DELETE /historico/{id}`: Remove registro do histórico.

### Relatórios (`/relatorios`)
- `GET /relatorios/disciplinas-mais-procuradas?semestre={semestre}`: Disciplinas ordenadas pelo total de solicitações no semestre.
- `GET /relatorios/taxa-reprovacao?semestre={semestre}`: Taxa percentual de reprovação por disciplina no histórico.
- `GET /relatorios/ocupacao-departamentos?semestre={semestre}`: Ocupação geral e detalhada de vagas agrupadas por departamento.

---

## 🛠️ Instalação e Execução

### Pré-requisitos
- Python 3.10+ (testado em Python 3.12)
- Pip

### 1. Navegar até a pasta do projeto
```bash
cd C:\tcc\coleta\antigravity_matricula_s2
```

### 2. Instalar dependências
```bash
pip install -r requirements.txt
```

### 3. Executar o servidor FastAPI
```bash
python run.py
```
O servidor estará disponível em: `http://localhost:8000`
- Documentação Interativa Swagger UI: `http://localhost:8000/docs`
- Documentação ReDoc: `http://localhost:8000/redoc`

### 4. Executar os Testes Automatizados
```bash
pytest -v
```
Todos os 32 testes unitários e de integração serão executados com banco de dados em memória isolado.
