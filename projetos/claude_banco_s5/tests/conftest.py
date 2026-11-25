import os
os.environ.setdefault("DATABASE_URL", "sqlite://")

import itertools
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import clock
from app.database import Base, get_db
from app.main import app


class Relogio:
    def __init__(self, inicio: datetime):
        self.atual = inicio

    def __call__(self):
        return self.atual

    def avancar(self, **kw):
        self.atual += timedelta(**kw)


@pytest.fixture
def relogio(monkeypatch):
    r = Relogio(datetime(2026, 11, 18, 10, 0, 0))
    monkeypatch.setattr(clock, "agora", r)
    return r


@pytest.fixture
def client(relogio):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _get_db():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


_seq = itertools.count(100000000)


def gerar_cpf() -> str:
    base = f"{next(_seq):09d}"
    for n in (9, 10):
        soma = sum(int(base[i]) * (n + 1 - i) for i in range(n))
        base += str((soma * 10) % 11 % 10)
    return base


@pytest.fixture
def novo_cliente(client):
    def _f(categoria="comum", **kw):
        cpf = gerar_cpf()
        r = client.post("/clientes", json={"nome": "Fulano de Tal", "cpf": cpf,
                                           "email": f"c{cpf}@ex.com", "categoria": categoria, **kw})
        assert r.status_code == 201, r.text
        return r.json()
    return _f


@pytest.fixture
def nova_conta(client, novo_cliente):
    def _f(categoria="comum", cliente_id=None, saldo="0", limite_credito="0", tipo="corrente"):
        if cliente_id is None:
            cliente_id = novo_cliente(categoria)["id"]
        r = client.post("/contas", json={"cliente_id": cliente_id, "tipo": tipo,
                                         "limite_credito": limite_credito})
        assert r.status_code == 201, r.text
        conta = r.json()
        if float(saldo) > 0:
            d = client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": saldo})
            assert d.status_code == 201, d.text
        return client.get(f"/contas/{conta['id']}").json()
    return _f
