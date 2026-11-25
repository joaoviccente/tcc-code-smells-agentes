import os
import sqlite3
from contextlib import contextmanager

ESQUEMA = """
CREATE TABLE IF NOT EXISTS alunos (
    id INTEGER PRIMARY KEY, nome TEXT NOT NULL, matricula TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE, categoria TEXT NOT NULL, situacao TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS disciplinas (
    id INTEGER PRIMARY KEY, codigo TEXT NOT NULL UNIQUE, nome TEXT NOT NULL,
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
    confirmada_em TEXT, prazo_confirmacao TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS matricula_vigente ON matriculas(aluno_id, turma_id)
    WHERE estado IN ('solicitada', 'confirmada', 'lista_de_espera');
CREATE INDEX IF NOT EXISTS matriculas_turma ON matriculas(turma_id, estado, data);
CREATE TABLE IF NOT EXISTS pre_requisitos (
    disciplina_id INTEGER NOT NULL REFERENCES disciplinas(id),
    exigida_id INTEGER NOT NULL REFERENCES disciplinas(id),
    PRIMARY KEY (disciplina_id, exigida_id)
);
CREATE TABLE IF NOT EXISTS historico (
    id INTEGER PRIMARY KEY, aluno_id INTEGER NOT NULL REFERENCES alunos(id),
    disciplina_id INTEGER NOT NULL REFERENCES disciplinas(id), semestre TEXT NOT NULL,
    nota REAL, situacao TEXT NOT NULL, motivo TEXT,
    matricula_id INTEGER UNIQUE REFERENCES matriculas(id)
);
CREATE INDEX IF NOT EXISTS historico_aluno ON historico(aluno_id, disciplina_id, situacao);
CREATE TABLE IF NOT EXISTS periodos_encerrados (semestre TEXT PRIMARY KEY);
"""


def conectar():
    db = sqlite3.connect(os.getenv("MATRICULAS_DB", "matriculas.sqlite3"), timeout=15, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def inicializar():
    db = conectar()
    try:
        db.executescript(ESQUEMA)
    finally:
        db.close()

@contextmanager
def transacao():
    db = conectar()
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            yield db
    finally:
        db.close()



