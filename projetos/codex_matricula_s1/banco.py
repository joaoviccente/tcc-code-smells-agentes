import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

BANCO = Path(os.getenv("MATRICULAS_DB", "matriculas.sqlite3"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS alunos (
    id INTEGER PRIMARY KEY, nome TEXT NOT NULL, matricula TEXT UNIQUE NOT NULL,
    email TEXT COLLATE NOCASE UNIQUE NOT NULL, categoria TEXT NOT NULL, situacao TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS disciplinas (
    id INTEGER PRIMARY KEY, codigo TEXT UNIQUE NOT NULL, nome TEXT NOT NULL,
    creditos INTEGER NOT NULL, carga_horaria INTEGER NOT NULL, departamento TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turmas (
    id INTEGER PRIMARY KEY, disciplina_id INTEGER NOT NULL REFERENCES disciplinas(id),
    semestre TEXT NOT NULL, professor TEXT NOT NULL, vagas INTEGER NOT NULL,
    horario TEXT NOT NULL, estado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS matriculas (
    id INTEGER PRIMARY KEY, aluno_id INTEGER NOT NULL REFERENCES alunos(id),
    turma_id INTEGER NOT NULL REFERENCES turmas(id), data TEXT NOT NULL, estado TEXT NOT NULL,
    confirmada_em TEXT, oferta_expira_em TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS matricula_vigente ON matriculas(aluno_id, turma_id)
    WHERE estado IN ('solicitada', 'confirmada', 'lista_de_espera');
CREATE INDEX IF NOT EXISTS matricula_turma ON matriculas(turma_id, estado);
CREATE INDEX IF NOT EXISTS matricula_aluno ON matriculas(aluno_id, estado);
CREATE TABLE IF NOT EXISTS prerequisitos (
    disciplina_id INTEGER NOT NULL REFERENCES disciplinas(id),
    disciplina_exigida_id INTEGER NOT NULL REFERENCES disciplinas(id),
    PRIMARY KEY (disciplina_id, disciplina_exigida_id),
    CHECK (disciplina_id <> disciplina_exigida_id)
);
CREATE TABLE IF NOT EXISTS historico (
    id INTEGER PRIMARY KEY, aluno_id INTEGER NOT NULL REFERENCES alunos(id),
    disciplina_id INTEGER NOT NULL REFERENCES disciplinas(id),
    semestre TEXT NOT NULL, nota REAL, situacao TEXT NOT NULL, motivo TEXT,
    matricula_id INTEGER UNIQUE REFERENCES matriculas(id)
);
CREATE INDEX IF NOT EXISTS historico_aluno ON historico(aluno_id, disciplina_id, situacao);
CREATE TABLE IF NOT EXISTS periodos_encerrados (semestre TEXT PRIMARY KEY);
"""


@contextmanager
def conexao():
    db = sqlite3.connect(BANCO, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys = ON")
        yield db
    finally:
        db.close()


def inicializar():
    with conexao() as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript(SCHEMA)


@contextmanager
def transacao():
    with conexao() as db, db:
        db.execute("BEGIN IMMEDIATE")
        yield db
