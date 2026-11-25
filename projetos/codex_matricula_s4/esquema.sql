CREATE TABLE IF NOT EXISTS alunos (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    matricula TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    categoria TEXT NOT NULL CHECK (categoria IN ('graduacao', 'pos', 'especial')),
    situacao TEXT NOT NULL CHECK (situacao IN ('ativo', 'trancado', 'jubilado'))
);
CREATE TABLE IF NOT EXISTS disciplinas (
    id INTEGER PRIMARY KEY,
    codigo TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    creditos INTEGER NOT NULL CHECK (creditos > 0),
    carga_horaria INTEGER NOT NULL CHECK (carga_horaria > 0),
    departamento TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turmas (
    id INTEGER PRIMARY KEY,
    disciplina_id INTEGER NOT NULL REFERENCES disciplinas(id),
    semestre TEXT NOT NULL,
    professor TEXT NOT NULL,
    vagas INTEGER NOT NULL CHECK (vagas > 0),
    dia INTEGER NOT NULL CHECK (dia BETWEEN 1 AND 7),
    inicio TEXT NOT NULL,
    fim TEXT NOT NULL CHECK (fim > inicio),
    estado TEXT NOT NULL CHECK (estado IN ('aberta', 'lotada', 'cancelada', 'encerrada'))
);
CREATE TABLE IF NOT EXISTS matriculas (
    id INTEGER PRIMARY KEY,
    aluno_id INTEGER NOT NULL REFERENCES alunos(id),
    turma_id INTEGER NOT NULL REFERENCES turmas(id),
    data TEXT NOT NULL,
    estado TEXT NOT NULL CHECK (estado IN ('solicitada', 'confirmada', 'lista_de_espera', 'cancelada', 'trancada')),
    oferta_ate TEXT,
    confirmada_em TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS matricula_ativa ON matriculas(aluno_id, turma_id)
    WHERE estado IN ('solicitada', 'confirmada', 'lista_de_espera');
CREATE INDEX IF NOT EXISTS matriculas_turma ON matriculas(turma_id, estado);
CREATE INDEX IF NOT EXISTS matriculas_aluno ON matriculas(aluno_id, estado);
CREATE TABLE IF NOT EXISTS pre_requisitos (
    disciplina_id INTEGER NOT NULL REFERENCES disciplinas(id),
    exigida_id INTEGER NOT NULL REFERENCES disciplinas(id),
    PRIMARY KEY (disciplina_id, exigida_id),
    CHECK (disciplina_id <> exigida_id)
);
CREATE TABLE IF NOT EXISTS historico (
    id INTEGER PRIMARY KEY,
    aluno_id INTEGER NOT NULL REFERENCES alunos(id),
    disciplina_id INTEGER NOT NULL REFERENCES disciplinas(id),
    semestre TEXT NOT NULL,
    nota REAL CHECK (nota BETWEEN 0 AND 10),
    situacao TEXT NOT NULL CHECK (situacao IN ('aprovado', 'reprovado', 'trancado')),
    motivo TEXT,
    matricula_id INTEGER UNIQUE REFERENCES matriculas(id)
);
CREATE INDEX IF NOT EXISTS historico_aluno_disciplina ON historico(aluno_id, disciplina_id, situacao);
CREATE TABLE IF NOT EXISTS periodos_encerrados (
    semestre TEXT PRIMARY KEY,
    encerrado_em TEXT NOT NULL
);
