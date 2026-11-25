import os
import random
import tempfile
from datetime import datetime

_db = os.path.join(tempfile.mkdtemp(), "teste.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ["INTERVALO_ROTINAS_SEGUNDOS"] = "0"
os.environ["TARIFA_POR_TRANSACAO"] = "2.50"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import clock  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

AGORA = datetime(2026, 11, 17, 10, 0, 0)


def gerar_cpf() -> str:
    base = [random.randint(0, 9) for _ in range(9)]
    for n in (9, 10):
        soma = sum(base[i] * (n + 1 - i) for i in range(n))
        base.append((soma * 10 % 11) % 10)
    cpf = "".join(map(str, base))
    return gerar_cpf() if cpf == cpf[0] * 11 else cpf


@pytest.fixture(autouse=True)
def banco_limpo():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    clock.fixar(AGORA)
    yield
    clock.fixar(None)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def novo_cliente(client):
    def _criar(categoria="comum", **extra):
        cpf = gerar_cpf()
        r = client.post("/clientes", json={
            "nome": extra.get("nome", "Cliente Teste"), "cpf": cpf,
            "email": f"c{cpf}@exemplo.com", "categoria": categoria,
        })
        assert r.status_code == 201, r.text
        return r.json()
    return _criar


@pytest.fixture
def nova_conta(client, novo_cliente):
    def _criar(categoria="comum", cliente=None, limite="0", saldo=None, tipo="corrente"):
        cliente = cliente or novo_cliente(categoria)
        r = client.post("/contas", json={
            "cliente_id": cliente["id"], "tipo": tipo, "limite_credito": limite,
        })
        assert r.status_code == 201, r.text
        conta = r.json()
        if saldo:
            r = client.post("/transacoes/depositos", json={"conta_id": conta["id"], "valor": saldo})
            assert r.status_code == 201, r.text
        return conta
    return _criar
