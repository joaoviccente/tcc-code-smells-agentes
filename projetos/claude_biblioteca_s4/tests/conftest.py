from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import clock, database
from app.main import app


class Relogio:
    def __init__(self, inicio: datetime):
        self.atual = inicio

    def __call__(self) -> datetime:
        return self.atual

    def avancar(self, dias: int = 0, horas: int = 0) -> None:
        self.atual += timedelta(days=dias, hours=horas)


@pytest.fixture
def relogio():
    r = Relogio(datetime(2026, 3, 2, 10, 0, 0))
    clock.definir_relogio(r)
    yield r
    clock.definir_relogio(None)


@pytest.fixture
def client(relogio, monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(
        database, "SessionLocal", sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    )
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ fabricas
ISBNS = ["9788535902778", "9780306406157", "9780131103627", "9780262033848", "9788575224779"]


class Fabrica:
    def __init__(self, client):
        self.c = client
        self.n = 0

    def usuario(self, categoria="aluno", **kw):
        self.n += 1
        dados = {
            "nome": f"Usuario {self.n}",
            "email": f"u{self.n}@uni.br",
            "matricula": f"M{self.n:05d}",
            "categoria": categoria,
            **kw,
        }
        r = self.c.post("/usuarios", json=dados)
        assert r.status_code == 201, r.text
        return r.json()

    def livro(self, area="Computacao", isbn=None):
        isbn = isbn or ISBNS[len(getattr(self, "_livros", []))]
        self._livros = getattr(self, "_livros", []) + [isbn]
        r = self.c.post("/livros", json={
            "titulo": f"Livro {isbn}", "autor": "Autor", "isbn": isbn, "ano": 2010,
            "area_conhecimento": area,
        })
        assert r.status_code == 201, r.text
        return r.json()

    def exemplar(self, livro_id, estado="disponivel"):
        self.n += 1
        r = self.c.post("/exemplares", json={"livro_id": livro_id, "codigo_tombo": f"T-{self.n}", "estado": estado})
        assert r.status_code == 201, r.text
        return r.json()

    def emprestar(self, usuario_id, exemplar_id, esperado=201):
        r = self.c.post("/emprestimos", json={"usuario_id": usuario_id, "exemplar_id": exemplar_id})
        assert r.status_code == esperado, r.text
        return r.json()

    def devolver(self, emp_id):
        r = self.c.post(f"/emprestimos/{emp_id}/devolucao")
        assert r.status_code == 200, r.text
        return r.json()

    def reservar(self, usuario_id, livro_id, esperado=201):
        r = self.c.post("/reservas", json={"usuario_id": usuario_id, "livro_id": livro_id})
        assert r.status_code == esperado, r.text
        return r.json()


@pytest.fixture
def f(client):
    return Fabrica(client)
