import os
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite://"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import database, relogio  # noqa: E402
from app.main import app  # noqa: E402

INICIO = datetime(2026, 3, 2, 10, 0, 0)


class Relogio:
    def __init__(self):
        self.atual = INICIO
        relogio.fixar(self.atual)

    def avancar(self, dias: int = 0, horas: int = 0):
        self.atual += timedelta(days=dias, hours=horas)
        relogio.fixar(self.atual)


@pytest.fixture
def tempo():
    r = Relogio()
    yield r
    relogio.fixar(None)


@pytest.fixture
def client(tempo):
    database.Base.metadata.drop_all(database.engine)
    database.Base.metadata.create_all(database.engine)
    with TestClient(app) as c:
        yield c


_seq = {"n": 0}


def _n():
    _seq["n"] += 1
    return _seq["n"]


def isbn13(base12: str) -> str:
    soma = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(base12))
    return base12 + str((10 - soma % 10) % 10)


@pytest.fixture
def fab(client):
    class Fabrica:
        def usuario(self, categoria="aluno", **kw):
            n = _n()
            r = client.post("/usuarios", json={"nome": f"Usuario {n}", "email": f"u{n}@uni.br",
                                                "matricula": f"M{n:05d}", "categoria": categoria, **kw})
            assert r.status_code == 201, r.text
            return r.json()

        def livro(self, area="Computacao", **kw):
            n = _n()
            r = client.post("/livros", json={"titulo": f"Livro {n}", "autor": "Autor", "isbn": isbn13(f"978{n:09d}"),
                                              "ano": 2020, "area_conhecimento": area, **kw})
            assert r.status_code == 201, r.text
            return r.json()

        def exemplar(self, livro_id, **kw):
            r = client.post("/exemplares", json={"livro_id": livro_id, "codigo_tombo": f"T{_n():06d}", **kw})
            assert r.status_code == 201, r.text
            return r.json()

        def emprestimo(self, usuario_id, exemplar_id):
            r = client.post("/emprestimos", json={"usuario_id": usuario_id, "exemplar_id": exemplar_id})
            assert r.status_code == 201, r.text
            return r.json()

    return Fabrica()
