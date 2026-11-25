from datetime import datetime, timedelta
from itertools import count

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import clock
from app.database import Base, get_db
from app.main import app


class Relogio:
    def __init__(self):
        self.atual = datetime(2026, 2, 1, 8, 0, 0)

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
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _db():
        s = Sessao()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    yield TestClient(app)
    app.dependency_overrides.clear()


_seq = count(1)


@pytest.fixture
def api(client):
    """Atalhos para montar cenarios."""

    class Api:
        c = client

        def aluno(self, categoria="graduacao", **kw):
            n = next(_seq)
            dados = {"nome": f"Aluno {n}", "matricula": f"A{n:05d}", "email": f"a{n}@uni.br",
                     "categoria": categoria, **kw}
            r = client.post("/alunos", json=dados)
            assert r.status_code == 201, r.text
            return r.json()

        def disciplina(self, creditos=4, departamento="DCC", **kw):
            n = next(_seq)
            dados = {"codigo": f"DIS{n:04d}", "nome": f"Disciplina {n}", "creditos": creditos,
                     "carga_horaria": creditos * 15, "departamento": departamento, **kw}
            r = client.post("/disciplinas", json=dados)
            assert r.status_code == 201, r.text
            return r.json()

        def turma(self, disciplina=None, vagas=40, horario=None, semestre="2026.1", **kw):
            disciplina = disciplina or self.disciplina()
            if horario is None:
                n = next(_seq)
                horario = [{"dia": ["seg", "ter", "qua", "qui", "sex", "sab"][n % 6],
                            "inicio": f"{7 + (n // 6) % 15:02d}:00", "fim": f"{7 + (n // 6) % 15:02d}:59"}]
            dados = {"disciplina_id": disciplina["id"], "semestre": semestre, "professor": "Prof. X",
                     "vagas": vagas, "horario": horario, **kw}
            r = client.post("/turmas", json=dados)
            assert r.status_code == 201, r.text
            return r.json()

        def solicitar(self, aluno, turma):
            return client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": turma["id"]})

        def matricular(self, aluno, turma):
            r = self.solicitar(aluno, turma)
            assert r.status_code == 201, r.text
            r = client.post(f"/matriculas/{r.json()['id']}/confirmar")
            assert r.status_code == 200, r.text
            return r.json()

        def historico(self, aluno, disciplina, situacao, nota=None, semestre="2025.2"):
            r = client.post(f"/alunos/{aluno['id']}/historico", json={
                "disciplina_id": disciplina["id"], "semestre": semestre, "situacao": situacao, "nota": nota})
            assert r.status_code == 201, r.text
            return r.json()

    return Api()
