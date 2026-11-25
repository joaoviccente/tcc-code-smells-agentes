import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.cliente import Cliente
from app.models.conta import Conta
from app.models.cartao import Cartao
from app.config import (
    CategoriaCliente,
    SituacaoCliente,
    TipoConta,
    EstadoConta,
    EstadoCartao,
)

# Banco SQLite em memória com StaticPool para compartilhar entre conexões de teste
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def cliente_comum(db):
    cliente = Cliente(
        nome="João da Silva",
        cpf="12345678909",
        email="joao@example.com",
        categoria=CategoriaCliente.COMUM,
        situacao=SituacaoCliente.ATIVO,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


@pytest.fixture
def cliente_premium(db):
    cliente = Cliente(
        nome="Maria Fernandes",
        cpf="23456789092",
        email="maria@example.com",
        categoria=CategoriaCliente.PREMIUM,
        situacao=SituacaoCliente.ATIVO,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


@pytest.fixture
def cliente_empresarial(db):
    cliente = Cliente(
        nome="Tech Solutions LTDA",
        cpf="34567890175",
        email="contato@techsolutions.com",
        categoria=CategoriaCliente.EMPRESARIAL,
        situacao=SituacaoCliente.ATIVO,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


@pytest.fixture
def conta_comum(db, cliente_comum):
    conta = Conta(
        cliente_id=cliente_comum.id,
        numero="0001-1",
        tipo=TipoConta.CORRENTE,
        saldo=Decimal("2000.00"),
        limite_credito=Decimal("500.00"),
        estado=EstadoConta.ATIVA,
    )
    db.add(conta)
    db.commit()
    db.refresh(conta)
    return conta


@pytest.fixture
def conta_premium(db, cliente_premium):
    conta = Conta(
        cliente_id=cliente_premium.id,
        numero="0002-2",
        tipo=TipoConta.CORRENTE,
        saldo=Decimal("10000.00"),
        limite_credito=Decimal("5000.00"),
        estado=EstadoConta.ATIVA,
    )
    db.add(conta)
    db.commit()
    db.refresh(conta)
    return conta


@pytest.fixture
def cartao_comum(db, conta_comum):
    cartao = Cartao(
        conta_id=conta_comum.id,
        numero="4111111111111111",
        limite=Decimal("3000.00"),
        estado=EstadoCartao.ATIVO,
    )
    db.add(cartao)
    db.commit()
    db.refresh(cartao)
    return cartao
