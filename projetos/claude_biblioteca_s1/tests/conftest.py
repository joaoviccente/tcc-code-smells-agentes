import os

os.environ["DATABASE_URL"] = "sqlite://"  # banco em memoria isolado para testes

from datetime import datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import relogio  # noqa: E402
from app.database import Base, engine  # noqa: E402
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
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)


_seq = {"n": 0}


def _prox():
    _seq["n"] += 1
    return _seq["n"]


def isbn13(n: int) -> str:
    base = f"978{n:09d}"
    soma = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(base))
    return base + str((10 - soma % 10) % 10)


@pytest.fixture
def api(client):
    class Api:
        c = client

        def usuario(self, categoria="aluno", **kw):
            n = _prox()
            body = {"nome": f"Usuario {n}", "email": f"u{n}@uni.br", "matricula": f"M{n:05d}",
                    "categoria": categoria, **kw}
            r = client.post("/usuarios", json=body)
            assert r.status_code == 201, r.text
            return r.json()

        def livro(self, area="Computacao", isbn=None):
            n = _prox()
            r = client.post("/livros", json={"titulo": f"Livro {n}", "autor": "Autor", "ano": 2010,
                                             "area": area, "isbn": isbn or isbn13(n)})
            assert r.status_code == 201, r.text
            return r.json()

        def exemplar(self, livro_id, estado="disponivel"):
            r = client.post("/exemplares", json={"livro_id": livro_id, "codigo_tombo": f"T{_prox()}",
                                                 "estado": estado})
            assert r.status_code == 201, r.text
            return r.json()

        def emprestar(self, usuario_id, exemplar_id, esperado=201):
            r = client.post("/emprestimos", json={"usuario_id": usuario_id, "exemplar_id": exemplar_id})
            assert r.status_code == esperado, r.text
            return r.json()

        def devolver(self, emp_id, esperado=200):
            r = client.post(f"/emprestimos/{emp_id}/devolucao")
            assert r.status_code == esperado, r.text
            return r.json()

        def reservar(self, usuario_id, livro_id, esperado=201):
            r = client.post("/reservas", json={"usuario_id": usuario_id, "livro_id": livro_id})
            assert r.status_code == esperado, r.text
            return r.json()

        def get(self, url):
            r = client.get(url)
            assert r.status_code == 200, r.text
            return r.json()

    return Api()
