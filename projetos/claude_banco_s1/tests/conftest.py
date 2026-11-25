from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import clock
from app.database import Base, get_db
from app.main import app

AGORA = datetime(2026, 11, 17, 10, 0, 0)

@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _db():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    clock.fixar(AGORA)
    with TestClient(app) as c:
        yield c
    clock.fixar(None)
    app.dependency_overrides.clear()


@pytest.fixture
def novo_cliente(client):
    contador = iter(range(1000))

    def _criar(categoria="comum", cpf=None):
        n = next(contador)
        r = client.post(
            "/clientes",
            json={
                "nome": f"Cliente {n}",
                "cpf": cpf or next(CPFS_POOL),
                "email": f"cliente{n}@banco.com.br",
                "categoria": categoria,
            },
        )
        assert r.status_code == 201, r.text
        return r.json()

    CPFS_POOL = iter(
        [
            "52998224725",
            "11144477735",
            "12345678909",
            "98765432100",
            "39053344705",
            "15350946056",
            "71428793860",
            "86288366757",
        ]
    )
    return _criar


@pytest.fixture
def nova_conta(client, novo_cliente):
    def _criar(categoria="comum", saldo=0, limite_credito=0, cliente_id=None):
        if cliente_id is None:
            cliente_id = novo_cliente(categoria)["id"]
        r = client.post(
            "/contas", json={"cliente_id": cliente_id, "tipo": "corrente", "limite_credito": limite_credito}
        )
        assert r.status_code == 201, r.text
        conta = r.json()
        if saldo:
            r = client.post("/transacoes/deposito", json={"conta_id": conta["id"], "valor": saldo})
            assert r.status_code == 201, r.text
            conta = client.get(f"/contas/{conta['id']}").json()
        return conta

    return _criar
