import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app

# Configuração de banco de dados SQLite em memória para testes
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Cria uma nova sessão de banco de dados em memória para cada teste."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Cliente de teste do FastAPI utilizando a sessão de banco de dados isolada."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def gerar_cpf(seed: int = 1) -> str:
    """Gera um CPF válido determinístico com base em uma semente inteira."""
    import random
    r = random.Random(seed)
    digits = [r.randint(0, 9) for _ in range(9)]
    s1 = sum(digits[i] * (10 - i) for i in range(9))
    r1 = (s1 * 10) % 11
    d1 = 0 if r1 == 10 else r1
    digits.append(d1)
    s2 = sum(digits[i] * (11 - i) for i in range(10))
    r2 = (s2 * 10) % 11
    d2 = 0 if r2 == 10 else r2
    digits.append(d2)
    return "".join(map(str, digits))

