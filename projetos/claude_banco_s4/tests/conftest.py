import os
from datetime import datetime

os.environ["BANCO_DATABASE_URL"] = "sqlite://"
os.environ["BANCO_ROTINA_AUTOMATICA"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from banco import clock  # noqa: E402
from banco.database import Base, engine  # noqa: E402
from banco.main import app  # noqa: E402

CPFS = ["52998224725", "11144477735", "39053344705", "16899535009", "71428793860", "87748248800"]


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    clock.definir(datetime(2026, 3, 10, 10, 0, 0))
    with TestClient(app) as c:
        yield c
    clock.definir(None)


@pytest.fixture
def fabrica(client):
    contador = {"n": 0}

    class F:
        def cliente(self, categoria="comum", **kw):
            i = contador["n"]
            contador["n"] += 1
            body = {"nome": f"Cliente {i}", "cpf": CPFS[i], "email": f"c{i}@ex.com", "categoria": categoria, **kw}
            r = client.post("/clientes", json=body)
            assert r.status_code == 201, r.text
            return r.json()

        def conta(self, cliente_id, tipo="corrente", limite_credito=0, saldo=0):
            r = client.post("/contas", json={"cliente_id": cliente_id, "tipo": tipo, "limite_credito": limite_credito})
            assert r.status_code == 201, r.text
            conta = r.json()
            if saldo:
                d = client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": saldo})
                assert d.status_code == 201, d.text
            return conta

        def cartao(self, conta_id, limite=1000):
            r = client.post("/cartoes", json={"conta_id": conta_id, "limite": limite})
            assert r.status_code == 201, r.text
            return r.json()

    return F()


def saldo(client, conta_id):
    return client.get(f"/contas/{conta_id}").json()["saldo"]
