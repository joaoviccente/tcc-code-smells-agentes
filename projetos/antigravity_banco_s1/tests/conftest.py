import os
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

# Configuração de banco em memória para testes isolados
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def gerar_cpf_valido(seed_num: int = 1) -> str:
    """Gera um CPF válido determinístico baseado em um número inteiro."""
    base_9 = f"{seed_num:09d}"[-9:]
    # Se todos forem iguais, incrementa
    if len(set(base_9)) == 1:
        base_9 = f"{seed_num + 12345:09d}"[-9:]

    # Primeiro dígito verificador
    soma1 = sum(int(base_9[i]) * (10 - i) for i in range(9))
    r1 = (soma1 * 10) % 11
    d1 = 0 if r1 in (10, 11) else r1

    # Segundo dígito verificador
    base_10 = base_9 + str(d1)
    soma2 = sum(int(base_10[i]) * (11 - i) for i in range(10))
    r2 = (soma2 * 10) % 11
    d2 = 0 if r2 in (10, 11) else r2

    return base_9 + str(d1) + str(d2)
