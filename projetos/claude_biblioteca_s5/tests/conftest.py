from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import clock, database
from app.main import app

INICIO = datetime(2026, 3, 2, 10, 0, 0)


@pytest.fixture()
def client(monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(eng, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    monkeypatch.setattr(database, "engine", eng)
    monkeypatch.setattr(database, "SessionLocal",
                        sessionmaker(bind=eng, autoflush=False, expire_on_commit=False))
    clock.fixar(INICIO)
    with TestClient(app) as c:
        yield c
    clock.resetar()
    database.Base.metadata.drop_all(eng)


class Fabrica:
    def __init__(self, client):
        self.c = client
        self.n = 0

    def _seq(self):
        self.n += 1
        return self.n

    def usuario(self, categoria="aluno", **kw):
        i = self._seq()
        dados = {"nome": f"Usuario {i}", "email": f"u{i}@universidade.edu.br",
                 "matricula": f"M{i:05d}", "categoria": categoria, **kw}
        r = self.c.post("/usuarios", json=dados)
        assert r.status_code == 201, r.text
        return r.json()

    def livro(self, area="Computacao", **kw):
        i = self._seq()
        dados = {"titulo": f"Livro {i}", "autor": "Autor", "isbn": isbn13(i),
                 "ano": 2020, "area_conhecimento": area, **kw}
        r = self.c.post("/livros", json=dados)
        assert r.status_code == 201, r.text
        return r.json()

    def exemplar(self, livro_id, **kw):
        i = self._seq()
        r = self.c.post("/exemplares", json={"livro_id": livro_id, "codigo_tombo": f"T{i:06d}", **kw})
        assert r.status_code == 201, r.text
        return r.json()

    def emprestar(self, usuario_id, exemplar_id, esperado=201):
        r = self.c.post("/emprestimos", json={"usuario_id": usuario_id, "exemplar_id": exemplar_id})
        assert r.status_code == esperado, r.text
        return r.json()

    def devolver(self, emprestimo_id):
        r = self.c.post(f"/emprestimos/{emprestimo_id}/devolucao")
        assert r.status_code == 200, r.text
        return r.json()

    def reservar(self, usuario_id, livro_id, esperado=201):
        r = self.c.post("/reservas", json={"usuario_id": usuario_id, "livro_id": livro_id})
        assert r.status_code == esperado, r.text
        return r.json()


def isbn13(seq: int) -> str:
    base = f"978{seq:09d}"
    soma = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(base))
    return base + str((10 - soma % 10) % 10)


@pytest.fixture()
def f(client):
    return Fabrica(client)
