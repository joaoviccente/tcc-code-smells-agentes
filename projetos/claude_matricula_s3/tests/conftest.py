import os
from datetime import datetime

os.environ["DATABASE_URL"] = "sqlite://"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.deps import obter_agora  # noqa: E402
from app.main import app  # noqa: E402


class Relogio:
    def __init__(self):
        self.agora = datetime(2026, 2, 1, 10, 0, 0)

    def avancar(self, **delta):
        from datetime import timedelta

        self.agora += timedelta(**delta)


@pytest.fixture
def relogio():
    return Relogio()


@pytest.fixture
def client(relogio):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[obter_agora] = lambda: relogio.agora
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class Fabrica:
    def __init__(self, client):
        self.c = client
        self.seq = 0

    def _n(self):
        self.seq += 1
        return self.seq

    def aluno(self, categoria="graduacao", **kw):
        n = self._n()
        corpo = {"nome": f"Aluno {n}", "matricula": f"MAT{n:05d}", "email": f"a{n}@uni.br",
                 "categoria": categoria, **kw}
        r = self.c.post("/alunos", json=corpo)
        assert r.status_code == 201, r.text
        return r.json()

    def disciplina(self, creditos=4, departamento="DMAT", **kw):
        n = self._n()
        corpo = {"codigo": f"DSC{n:03d}", "nome": f"Disciplina {n}", "creditos": creditos,
                 "carga_horaria": creditos * 15, "departamento": departamento, **kw}
        r = self.c.post("/disciplinas", json=corpo)
        assert r.status_code == 201, r.text
        return r.json()

    def turma(self, disciplina_id=None, vagas=40, horarios=None, semestre="2026.1", **kw):
        if disciplina_id is None:
            disciplina_id = self.disciplina()["id"]
        if horarios is None:  # um horário único por turma, sem conflitos
            self.slot = getattr(self, "slot", -1) + 1
            dia = ["SEG", "TER", "QUA", "QUI", "SEX", "SAB"][self.slot // 15]
            h = 7 + self.slot % 15
            horarios = [{"dia": dia, "inicio": f"{h:02d}:00", "fim": f"{h:02d}:59"}]
        corpo = {"disciplina_id": disciplina_id, "semestre": semestre, "professor": "Prof X",
                 "vagas": vagas, "horarios": horarios, **kw}
        r = self.c.post("/turmas", json=corpo)
        assert r.status_code == 201, r.text
        return r.json()

    def solicitar(self, aluno_id, turma_id, esperado=201):
        r = self.c.post("/matriculas", json={"aluno_id": aluno_id, "turma_id": turma_id})
        assert r.status_code == esperado, r.text
        return r.json()

    def matricular(self, aluno_id, turma_id):
        m = self.solicitar(aluno_id, turma_id)["matricula"]
        r = self.c.post(f"/matriculas/{m['id']}/confirmar")
        assert r.status_code == 200, r.text
        return r.json()["matricula"]

    def historico(self, aluno_id, disciplina_id, situacao, nota=None, semestre="2025.2"):
        if nota is None and situacao != "trancado":
            nota = 8.0 if situacao == "aprovado" else 2.0
        r = self.c.post(f"/alunos/{aluno_id}/historico", json={
            "disciplina_id": disciplina_id, "semestre": semestre, "situacao": situacao, "nota": nota})
        assert r.status_code == 201, r.text
        return r.json()


@pytest.fixture
def f(client):
    return Fabrica(client)
