import itertools

import pytest
from fastapi.testclient import TestClient

from app import clock, database

database.configurar("sqlite://")

from app.main import app  # noqa: E402

_seq = itertools.count(1)
_slots = itertools.count(0)
DIAS = ["SEG", "TER", "QUA", "QUI", "SEX", "SAB"]


def _slot_unico():
    """Horario distinto a cada chamada, para evitar conflitos acidentais."""
    n = next(_slots) % 84
    h = 7 + n // 6
    return [{"dia": DIAS[n % 6], "inicio": f"{h:02d}:00", "fim": f"{h:02d}:50"}]


@pytest.fixture()
def client():
    database.Base.metadata.drop_all(database.engine)
    database.criar_tabelas()
    clock.reiniciar()
    global _slots
    _slots = itertools.count(0)
    with TestClient(app) as c:
        yield c
    clock.reiniciar()


@pytest.fixture()
def fab(client):
    """Fabrica de entidades para os testes."""

    class Fab:
        def aluno(self, categoria="graduacao", **kw):
            n = next(_seq)
            dados = {
                "nome": f"Aluno {n}",
                "matricula": f"MAT{n:05d}",
                "email": f"aluno{n}@uni.br",
                "categoria": categoria,
                **kw,
            }
            r = client.post("/alunos", json=dados)
            assert r.status_code == 201, r.text
            return r.json()

        def disciplina(self, creditos=4, departamento="DCC", **kw):
            n = next(_seq)
            dados = {
                "codigo": f"DSC{n:04d}",
                "nome": f"Disciplina {n}",
                "creditos": creditos,
                "carga_horaria": creditos * 15,
                "departamento": departamento,
                **kw,
            }
            r = client.post("/disciplinas", json=dados)
            assert r.status_code == 201, r.text
            return r.json()

        def turma(self, disciplina=None, vagas=40, horario=None, semestre="2026.1", **kw):
            disciplina = disciplina or self.disciplina()
            dados = {
                "disciplina_id": disciplina["id"],
                "semestre": semestre,
                "professor": "Prof. Silva",
                "vagas": vagas,
                "horario": horario or _slot_unico(),
                **kw,
            }
            r = client.post("/turmas", json=dados)
            assert r.status_code == 201, r.text
            return r.json()

        def matricular(self, aluno, turma, confirmar=True, esperado=201):
            r = client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": turma["id"]})
            assert r.status_code == esperado, r.text
            m = r.json()
            if confirmar and m["estado"] == "solicitada":
                r = client.post(f"/matriculas/{m['id']}/confirmar")
                assert r.status_code == 200, r.text
                m = r.json()
            return m

        def historico(self, aluno, disciplina, situacao, nota=None, semestre="2025.2"):
            if nota is None and situacao != "trancado":
                nota = 8.0 if situacao == "aprovado" else 2.0
            r = client.post(
                "/historico",
                json={
                    "aluno_id": aluno["id"],
                    "disciplina_id": disciplina["id"],
                    "semestre": semestre,
                    "nota": nota,
                    "situacao": situacao,
                },
            )
            assert r.status_code == 201, r.text
            return r.json()

    return Fab()
