from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import clock
from app.database import Base, criar_engine, get_db
from app.main import app


class Relogio:
    def __init__(self):
        self.atual = datetime(2026, 11, 18, 10, 0, 0)

    def __call__(self):
        return self.atual

    def avancar(self, **kw):
        self.atual += timedelta(**kw)


@pytest.fixture
def relogio(monkeypatch):
    r = Relogio()
    monkeypatch.setattr(clock, "agora", r)
    return r


@pytest.fixture
def client(relogio):
    eng = criar_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(eng)
    Sessao = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)

    def _db():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


CPFS = ["52998224725", "11144477735", "12345678909", "98765432100", "39053344705",
        "28625587887", "71428793860", "86288366757", "45317828791", "16899535009"]


@pytest.fixture
def novo_cliente(client):
    disponiveis = iter(CPFS)

    def _f(categoria="comum", nome="Fulano de Tal"):
        r = client.post("/clientes", json={"nome": nome, "cpf": next(disponiveis),
                                           "email": "fulano@example.com", "categoria": categoria})
        assert r.status_code == 201, r.text
        return r.json()
    return _f


@pytest.fixture
def nova_conta(client):
    def _f(cliente_id, limite="0.00", saldo=None):
        r = client.post("/contas", json={"cliente_id": cliente_id, "limite_credito": limite})
        assert r.status_code == 201, r.text
        conta = r.json()
        if saldo:
            r = client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": saldo})
            assert r.status_code == 201, r.text
        return conta
    return _f
