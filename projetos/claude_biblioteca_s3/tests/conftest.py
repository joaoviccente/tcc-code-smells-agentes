from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import clock, database
from app.main import app

INICIO = datetime(2026, 3, 2, 10, 0, 0)


class Relogio:
    def __init__(self, inicio: datetime):
        self.atual = inicio
        clock.fixar(inicio)

    def avancar(self, dias: float = 0, horas: float = 0):
        self.atual += timedelta(days=dias, hours=horas)
        clock.fixar(self.atual)


@pytest.fixture
def relogio():
    r = Relogio(INICIO)
    yield r
    clock.fixar(None)


@pytest.fixture
def client(tmp_path, monkeypatch, relogio):
    eng = database.criar_engine(f"sqlite:///{tmp_path / 'teste.db'}")
    monkeypatch.setattr(database, "engine", eng)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=eng, expire_on_commit=False))
    with TestClient(app) as c:
        yield c
    eng.dispose()


_seq = {"n": 0}


def _prox():
    _seq["n"] += 1
    return _seq["n"]


def gerar_isbn13(n: int) -> str:
    base = f"978{n:09d}"
    soma = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(base))
    return base + str((10 - soma % 10) % 10)


@pytest.fixture
def fabrica(client):
    class F:
        def usuario(self, categoria="aluno", **kw):
            n = _prox()
            dados = {"nome": f"Usuario {n}", "email": f"u{n}@uni.br", "matricula": f"M{n}",
                     "categoria": categoria, **kw}
            r = client.post("/usuarios", json=dados)
            assert r.status_code == 201, r.text
            return r.json()

        def livro(self, area="Computacao", **kw):
            n = _prox()
            dados = {"titulo": f"Livro {n}", "autor": "Autor", "isbn": gerar_isbn13(n),
                     "ano": 2010, "area": area, **kw}
            r = client.post("/livros", json=dados)
            assert r.status_code == 201, r.text
            return r.json()

        def exemplar(self, livro_id, estado="disponivel"):
            r = client.post("/exemplares", json={"livro_id": livro_id, "tombo": f"T{_prox()}", "estado": estado})
            assert r.status_code == 201, r.text
            return r.json()

        def emprestar(self, usuario_id, exemplar_id, esperado=201):
            r = client.post("/emprestimos", json={"usuario_id": usuario_id, "exemplar_id": exemplar_id})
            assert r.status_code == esperado, r.text
            return r.json()

        def devolver(self, emprestimo_id):
            r = client.post(f"/emprestimos/{emprestimo_id}/devolucao")
            assert r.status_code == 200, r.text
            return r.json()

        def reservar(self, usuario_id, livro_id, esperado=201):
            r = client.post("/reservas", json={"usuario_id": usuario_id, "livro_id": livro_id})
            assert r.status_code == esperado, r.text
            return r.json()

        def multas(self, usuario_id):
            return client.get(f"/usuarios/{usuario_id}/multas").json()

        def get(self, url):
            r = client.get(url)
            assert r.status_code == 200, r.text
            return r.json()

    return F()
