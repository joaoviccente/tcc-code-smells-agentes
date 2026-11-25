import os

os.environ["DATABASE_URL"] = "sqlite://"  # evita criar o arquivo do banco real nos testes

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import clock
from app.database import Base, criar_engine, get_db
from app.main import app


@pytest.fixture()
def client():
    engine = criar_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)

    def _db():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    clock.resetar()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    clock.resetar()
    engine.dispose()


class Api:
    """Atalhos para montar cenarios."""

    def __init__(self, c):
        self.c = c
        self._n = 0

    def aluno(self, categoria="graduacao", **kw):
        self._n += 1
        dados = {"nome": f"Aluno {self._n}", "matricula": f"A{self._n:05d}",
                 "email": f"aluno{self._n}@uni.br", "categoria": categoria, **kw}
        r = self.c.post("/alunos", json=dados)
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def disciplina(self, creditos=4, departamento="DCC", pre=(), codigo=None):
        self._n += 1
        r = self.c.post("/disciplinas", json={
            "codigo": codigo or f"DIS{self._n:03d}", "nome": f"Disciplina {self._n}", "creditos": creditos,
            "carga_horaria": creditos * 15, "departamento": departamento, "pre_requisitos": list(pre)})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def turma(self, disciplina_id, vagas=40, dia="SEG", inicio="08:00", fim="10:00", semestre="2026.2"):
        r = self.c.post("/turmas", json={
            "disciplina_id": disciplina_id, "semestre": semestre, "professor": "Prof. X", "vagas": vagas,
            "horarios": [{"dia_semana": dia, "hora_inicio": inicio, "hora_fim": fim}]})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def historico(self, aluno_id, disciplina_id, situacao, nota=None, semestre="2026.1"):
        dados = {"disciplina_id": disciplina_id, "semestre": semestre, "situacao": situacao}
        if nota is not None:
            dados["nota"] = nota
        r = self.c.post(f"/alunos/{aluno_id}/historico", json=dados)
        assert r.status_code == 201, r.text

    def solicitar(self, aluno_id, turma_id):
        return self.c.post("/matriculas", json={"aluno_id": aluno_id, "turma_id": turma_id})

    def matricular(self, aluno_id, turma_id):
        r = self.solicitar(aluno_id, turma_id)
        assert r.status_code == 201, r.text
        mid = r.json()["id"]
        r = self.c.post(f"/matriculas/{mid}/confirmar")
        assert r.status_code == 200, r.text
        return mid


@pytest.fixture()
def api(client):
    return Api(client)
