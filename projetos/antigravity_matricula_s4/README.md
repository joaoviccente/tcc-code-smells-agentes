# API REST para Gestão de Matrículas Acadêmicas

API REST desenvolvida em Python (FastAPI + SQLAlchemy + Pydantic v2 + SQLite) para gestão completa de matrículas acadêmicas universitárias, contemplando regras de categorias de alunos, controle de créditos, gestão dinâmica de lista de espera com prioridades e janelas de 48 horas, detecção inteligente de conflitos de horário, verificação de pré-requisitos e reprovações, trancamento e cancelamento com penalidades e relatórios analíticos.

---

## 🏛️ Entidades do Sistema

- **Aluno**: Identificação (`nome`, `matricula` única, `email` único), `categoria` (`graduacao`, `pos`, `especial`) e `situacao` (`ativo`, `trancado`, `jubilado`).
- **Disciplina**: `codigo` único, `nome`, `numero_creditos`, `carga_horaria` e `departamento`.
- **Turma**: Pertence a uma disciplina, com `semestre`, `professor`, `numero_vagas`, `horario` estruturado e `estado` (`aberta`, `lotada`, `cancelada`, `encerrada`).
- **Matrícula**: Liga aluno a uma turma com `data` de solicitação e `estado` (`solicitada`, `confirmada`, `lista_de_espera`, `cancelada`, `trancada`). Registra `data_oferta_vaga` quando o aluno na fila recebe vaga liberada.
- **PreRequisito**: Liga uma disciplina à outra exigida, com validação anti-circularidade.
- **Histórico**: Registro acadêmico com `aluno`, `disciplina`, `semestre`, `nota` e `situacao` (`aprovado`, `reprovado`, `reprovado_por_falta`, `trancado`).

---

## 📋 Regras por Categoria de Aluno

| Categoria | Máx. Créditos / Semestre | Limite Trancamentos / Disciplina | Prazo Cancelamento | Prioridade na Fila de Espera |
| :--- | :---: | :---: | :---: | :---: |
| **Graduação** | **28** | Até **2** | **15 dias** | Média (2) |
| **Pós** | **16** | **1** | **30 dias** | Alta (1) |
| **Especial** | **8** | **0** (nenhum permitido) | **7 dias** | Baixa (3) |

---

## ⚙️ Regras de Negócio Implementadas

1. **Requisitos para Matrícula**:
   - Aluno deve estar com situação `ativo`.
   - Deve ter sido aprovado (`aprovado`) em todos os pré-requisitos da disciplina no histórico.
   - A soma dos créditos das turmas confirmadas no semestre com os créditos da nova disciplina não pode ultrapassar o teto da sua categoria.
2. **Turma Lotada e Lista de Espera**:
   - Vagas ocupadas >= `numero_vagas` faz a matrícula entrar em `lista_de_espera`.
   - Ordenação estrita: **Prioridade da Categoria** (Pós = 1, Graduação = 2, Especial = 3) e, em caso de empate, **Data da Solicitação** (mais antiga primeiro).
   - Quando uma vaga é liberada (por cancelamento ou trancamento), o 1º da fila entra em `solicitada` e tem **48 horas** para confirmar. Esgotado o prazo, é cancelada e a vez passa ao próximo.
3. **Limite de Reprovações**:
   - Aluno reprovado 3 vezes na mesma disciplina (reprovação normal ou reprovação por falta) fica impedido de se matricular nela novamente.
4. **Prazos de Trancamento e Cancelamento**:
   - O trancamento de disciplina só é permitido dentro do prazo de cancelamento da sua categoria e respeitando o limite de trancamentos por disciplina.
   - O cancelamento fora do prazo registra reprovação por falta (`reprovado_por_falta`) no histórico.
5. **Adesão Mínima da Turma**:
   - Turma com menos de 5 matrículas confirmadas ao encerramento do período de matrículas é cancelada (`cancelada`), e todas as suas matrículas tornam-se canceladas.
6. **Conflito de Horário**:
   - Matrícula em turma cujo horário conflite com outra turma já confirmada do aluno no mesmo semestre é sumariamente negada (HTTP 409 Conflict).
7. **Acúmulo de Trancamentos no Semestre**:
   - Aluno que acumular 3 trancamentos no semestre passa à situação `trancado`, e todas as suas matrículas confirmadas são canceladas, liberando suas vagas para a lista de espera.

---

## 🚀 Como Executar o Projeto

### Pré-requisitos
- Python 3.10 ou superior instalado.

### 1. Instalação das Dependências
```bash
pip install -r requirements.txt
```

### 2. Iniciar o Servidor da API
```bash
uvicorn app.main:app --reload --port 8000
```

### 3. Acessar a Documentação Interativa
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🧪 Executando a Suíte de Testes

Os testes automatizados cobrem 100% dos requisitos, endpoints e regras de negócio:

```bash
python -m pytest -v
```

---

## 📡 Endpoints da API

### Alunos
- `POST /alunos`: Cadastrar aluno.
- `GET /alunos`: Listar alunos (com filtros por categoria e situação).
- `GET /alunos/{id}`: Obter detalhes do aluno.
- `PUT /alunos/{id}`: Atualizar dados do aluno.
- `DELETE /alunos/{id}`: Excluir aluno.
- `GET /alunos/{id}/matriculas`: Listar todas as matrículas do aluno.
- `GET /alunos/{id}/historico`: Consultar histórico acadêmico do aluno.
- `POST /alunos/{id}/historico`: Lançar registro histórico para o aluno.

### Disciplinas e Pré-Requisitos
- `POST /disciplinas`: Cadastrar nova disciplina.
- `GET /disciplinas`: Listar disciplinas cadastradas.
- `GET /disciplinas/{id}`: Obter dados da disciplina e seus pré-requisitos.
- `PUT /disciplinas/{id}`: Atualizar disciplina.
- `DELETE /disciplinas/{id}`: Remover disciplina.
- `POST /disciplinas/{id}/pre-requisitos`: Vincular disciplina exigida como pré-requisito (valida dependências circulares).
- `GET /disciplinas/{id}/pre-requisitos`: Listar pré-requisitos da disciplina.
- `DELETE /disciplinas/{id}/pre-requisitos/{pre_requisito_id}`: Remover pré-requisito.

### Turmas
- `POST /turmas`: Cadastrar turma (validação de formato de horário: ex: `SEG 08:00-10:00, QUA 08:00-10:00`).
- `GET /turmas`: Listar turmas (filtros por semestre, disciplina, estado).
- `GET /turmas/{id}`: Obter turma, incluindo vagas ocupadas e disponíveis.
- `PUT /turmas/{id}`: Atualizar turma.
- `DELETE /turmas/{id}`: Remover turma.
- `GET /turmas/{id}/fila`: Consultar a fila de espera ordenada por categoria e data, com prazos de 48h.
- `POST /turmas/{id}/encerrar-periodo`: Encerra período de matrícula da turma (Regra 5: cancela se < 5 confirmadas).
- `POST /turmas/encerrar-periodo-semestre`: Aplica a Regra 5 para todo o semestre letivo.

### Matrículas
- `POST /matriculas/solicitar` (ou `POST /matriculas`): Solicitar matrícula (confirma se houver vaga ou entra na fila se lotada).
- `POST /matriculas/{id}/confirmar`: Confirmar matrícula ofertada via lista de espera (valida janela de 48h).
- `POST /matriculas/{id}/cancelar`: Cancelar matrícula (registra reprovação por falta se fora do prazo da categoria).
- `POST /matriculas/{id}/trancar`: Trancar matrícula (valida prazos, limite por disciplina e trancamento automático no 3º trancamento do semestre).
- `GET /matriculas/aluno/{aluno_id}`: Listar matrículas por aluno.
- `GET /matriculas/{id}`: Obter dados de uma matrícula.
- `GET /matriculas`: Listar matrículas gerais com filtros.

### Histórico
- `POST /historico`: Cadastrar registro histórico.
- `GET /historico/aluno/{aluno_id}`: Consultar histórico por aluno.

### Relatórios Analíticos
- `GET /relatorios/disciplinas-mais-procuradas?semestre=2026.1`: Disciplinas mais procuradas no semestre (ordenadas por demanda).
- `GET /relatorios/taxa-reprovacao`: Taxa percentual de reprovação por disciplina no histórico.
- `GET /relatorios/ocupacao-departamentos?semestre=2026.1`: Taxa de ocupação de vagas agrupadas por departamento.
