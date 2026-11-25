# API REST de Gestão de Matrículas Acadêmicas

API REST desenvolvida em Python com **FastAPI**, **SQLAlchemy** e **Pydantic v2** para gestão de matrículas acadêmicas de uma universidade, respeitando rigorosamente regras de negócio institucionais, validação estrita de dados de entrada, persistência em banco relacional e tratamento completo de códigos de status HTTP.

---

## 🏛️ Entidades do Sistema

- **Aluno**: Nome, matrícula (única), e-mail (único), categoria (`graduacao`, `pos` ou `especial`) e situação (`ativo`, `trancado` ou `jubilado`).
- **Disciplina**: Código (único), nome, número de créditos, carga horária e departamento.
- **PreRequisito**: Associação auto-relacional muitos-para-muitos entre disciplinas.
- **Turma**: Pertence a uma disciplina, com semestre (ex: `2026.1`), professor, número de vagas, horário (ex: `SEG 08:00-10:00, QUA 08:00-10:00`) e estado (`aberta`, `lotada`, `cancelada`, `encerrada`).
- **Matrícula**: Aluno, turma, data de solicitação e estado (`solicitada`, `confirmada`, `lista_de_espera`, `cancelada`, `trancada`).
- **Histórico**: Aluno, disciplina, semestre, nota (0.0 a 10.0) e situação (`aprovado`, `reprovado`, `reprovado_por_falta`, `trancado`).

---

## 📋 Regras por Categoria de Aluno

| Categoria | Máx. Créditos / Semestre | Limite Trancamentos / Disciplina | Prazo de Cancelamento | Prioridade na Fila de Espera |
| :--- | :---: | :---: | :---: | :---: |
| **Graduação** | 28 créditos | Até 2 trancamentos | 15 dias | Média (Prioridade 2) |
| **Pós** | 16 créditos | 1 trancamento | 30 dias | Alta (Prioridade 1) |
| **Especial** | 8 créditos | Nenhum (0) | 7 dias | Baixa (Prioridade 3) |

---

## ⚖️ Regras de Negócio Implementadas

1. **Permissão de Matrícula**:
   - Apenas permitida a alunos com situação `ativo`.
   - Exige aprovação prévia (`situacao == 'aprovado'`) em todos os pré-requisitos da disciplina segundo o histórico.
   - Bloqueia solicitações que excedam o limite máximo de créditos da categoria no semestre.

2. **Lista de Espera e Janela de 48 Horas**:
   - Quando a turma estiver lotada, a matrícula entra automaticamente em `lista_de_espera`.
   - A fila é ordenada primariamente pela prioridade da categoria (Pós > Graduação > Especial) e, em caso de empate, pela data da solicitação (ordem cronológica).
   - Quando uma vaga é liberada (por cancelamento, trancamento ou expiração), o primeiro da fila é convocado com um prazo de **48 horas** para confirmar.
   - Esgotado o prazo de 48 horas sem confirmação, a matrícula é cancelada e a vaga passa automaticamente ao próximo da fila.

3. **Impedimento por 3 Reprovações**:
   - Aluno reprovado 3 vezes na mesma disciplina fica bloqueado de se matricular nela novamente.

4. **Trancamento vs. Cancelamento Fora do Prazo**:
   - Trancamento só é permitido dentro do prazo de cancelamento da categoria e respeitando o limite de trancamentos por disciplina. Gera registro `trancado` no histórico.
   - Cancelamento realizado dentro do prazo da categoria é cancelado sem penalidade acadêmica.
   - Fora do prazo da categoria, o cancelamento registra automaticamente **reprovação por falta** (`reprovado_por_falta`) no histórico acadêmico.

5. **Cancelamento de Turma com Menos de 5 Alunos**:
   - Turma com menos de 5 matrículas confirmadas ao encerramento do período de matrícula é cancelada, e todas as suas matrículas associadas passam ao estado `cancelada`.

6. **Conflito de Horários**:
   - Matrícula em turma cujo horário conflite com outra turma já confirmada do aluno no mesmo semestre é negada.

7. **Três Trancamentos no Semestre**:
   - Aluno que acumular 3 trancamentos no mesmo semestre passa automaticamente à situação `trancado`, e todas as suas demais matrículas confirmadas naquele semestre são canceladas (com liberação imediata das vagas para a fila de espera).

---

## 🚀 Como Executar o Projeto

### 1. Pré-requisitos
- Python 3.10+ instalado.

### 2. Instalação das Dependências
```bash
pip install -r requirements.txt
```

### 3. Popular Banco de Dados (Opcional)
Um script de seed está disponível para carregar dados iniciais de exemplo (alunos, disciplinas, pré-requisitos e turmas):
```bash
python seed.py
```

### 4. Executar a Aplicação
```bash
uvicorn app.main:app --reload
```
Acesse a documentação interativa em:
- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

### 5. Executar a Suíte de Testes
```bash
python -m pytest -v
```
Todos os 28 testes automatizados cobrem integralmente as regras de negócio, CRUDs, relatórios e casos de borda.

---

## 📡 Endpoints da API

### Alunos (`/alunos`)
- `POST /alunos` (201 Created): Cadastra um aluno.
- `GET /alunos` (200 OK): Lista alunos (filtros opcionais: `categoria`, `situacao`).
- `GET /alunos/{id}` (200 OK / 404 Not Found): Detalhes de um aluno.
- `PUT /alunos/{id}` (200 OK / 404 Not Found): Atualiza dados do aluno.
- `DELETE /alunos/{id}` (204 No Content / 404 Not Found): Remove um aluno.
- `GET /alunos/{id}/matriculas` (200 OK): Lista matrículas do aluno.
- `GET /alunos/{id}/historico` (200 OK): Consulta histórico completo do aluno.

### Disciplinas (`/disciplinas`)
- `POST /disciplinas` (201 Created): Cadastra disciplina e associa pré-requisitos.
- `GET /disciplinas` (200 OK): Lista disciplinas (filtro: `departamento`).
- `GET /disciplinas/{id}` (200 OK / 404 Not Found): Detalhes da disciplina e pré-requisitos.
- `PUT /disciplinas/{id}` (200 OK / 404 Not Found): Atualiza dados da disciplina.
- `DELETE /disciplinas/{id}` (204 No Content / 404 Not Found): Remove disciplina.
- `POST /disciplinas/{id}/prerequisitos/{prereq_id}` (201 Created): Adiciona pré-requisito.
- `DELETE /disciplinas/{id}/prerequisitos/{prereq_id}` (204 No Content): Remove pré-requisito.

### Turmas (`/turmas`)
- `POST /turmas` (201 Created / 400 Bad Request): Cria uma turma com validação de horário.
- `GET /turmas` (200 OK): Lista turmas com contagem de vagas ocupadas e restantes.
- `GET /turmas/{id}` (200 OK / 404 Not Found): Detalhes da turma.
- `PUT /turmas/{id}` (200 OK): Atualiza dados da turma.
- `DELETE /turmas/{id}` (204 No Content): Remove turma.
- `GET /turmas/{id}/fila` (200 OK): **Consulta a fila de espera da turma** com ordem de prioridade e prazos de 48h.
- `POST /turmas/{id}/processar-fila` (200 OK): Processa expirações de 48h e avança fila.
- `POST /turmas/{id}/encerrar-periodo-matricula` (200 OK): **Regra 5** (cancela turma se `< 5` matrículas confirmadas).

### Matrículas (`/matriculas`)
- `POST /matriculas/solicitar` (201 Created / 400 Bad Request / 409 Conflict): **Solicita matrícula** (aplica regras 1, 2, 3 e 6).
- `POST /matriculas/{id}/confirmar` (200 OK / 400 Bad Request): **Confirma matrícula** convocada da fila de espera dentro de 48h.
- `POST /matriculas/{id}/cancelar` (200 OK / 400 Bad Request): **Cancela matrícula** (Regra 4: fora do prazo registra reprovação por falta).
- `POST /matriculas/{id}/trancar` (200 OK / 400 Bad Request): **Tranca matrícula** (Regras 4 e 7: limite de trancamentos e trancamento por 3 ocorrências no semestre).
- `GET /matriculas/aluno/{aluno_id}` (200 OK): **Lista matrículas por aluno**.
- `GET /matriculas` (200 OK): Lista geral com filtros.
- `GET /matriculas/{id}` (200 OK): Detalhes completos com dados da turma e posição na fila se aplicável.

### Histórico Acadêmico (`/historico`)
- `POST /historico` (201 Created): Registra aprovação, reprovação ou nota.
- `GET /historico/aluno/{aluno_id}` (200 OK): **Consulta histórico por aluno**.
- `GET /historico` (200 OK): Consulta registros com filtros.
- `GET /historico/{id}` (200 OK): Detalhes de um registro.

### Relatórios (`/relatorios`)
- `GET /relatorios/disciplinas-mais-procuradas`: Disciplinas mais procuradas no semestre (total de solicitações, confirmadas e fila).
- `GET /relatorios/taxa-reprovacao`: Taxa de reprovação percentual por disciplina calculada sobre o histórico.
- `GET /relatorios/ocupacao-departamentos`: Taxa de ocupação das turmas agrupada por departamento.
