import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from fastapi import HTTPException


def conectar():
    banco = os.environ.get("MATRICULAS_DB", str(Path(__file__).with_name("matriculas.sqlite3")))
    db = sqlite3.connect(banco, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def inicializar():
    with closing(conectar()) as db:
        db.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8-sig"))


@contextmanager
def transacao(escrita=True):
    db = conectar()
    try:
        db.execute("BEGIN IMMEDIATE" if escrita else "BEGIN")
        yield db
        db.commit()
    except sqlite3.IntegrityError as erro:
        db.rollback()
        raise HTTPException(409, "Registro duplicado ou vinculado a outros registros.") from erro
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def buscar(db, tabela, id):
    item = db.execute(f"SELECT * FROM {tabela} WHERE id = ?", (id,)).fetchone()
    if item is None:
        raise HTTPException(404, "Registro nao encontrado.")
    return dict(item)


def inserir(db, tabela, dados):
    campos = ", ".join(dados)
    valores = ", ".join("?" for _ in dados)
    return db.execute(
        f"INSERT INTO {tabela} ({campos}) VALUES ({valores})", tuple(dados.values())
    ).lastrowid


def atualizar(db, tabela, id, dados):
    campos = ", ".join(f"{campo} = ?" for campo in dados)
    db.execute(f"UPDATE {tabela} SET {campos} WHERE id = ?", (*dados.values(), id))


