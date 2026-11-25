import pytest


def test_regra5_turma_com_menos_de_5_matriculas_cancelada(client):
    r_disc = client.post("/disciplinas", json={"codigo": "DCC700", "nome": "Compiladores", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"})
    disc_id = r_disc.json()["id"]

    r_turma = client.post("/turmas", json={"disciplina_id": disc_id, "semestre": "2026.1", "professor": "Dijkstra", "numero_vagas": 20, "horario": "SEX 08:00-10:00"})
    turma_id = r_turma.json()["id"]

    # Matricula apenas 3 alunos (< 5)
    matriculas_ids = []
    for i in range(3):
        a_id = client.post("/alunos", json={"nome": f"Aluno {i}", "matricula": f"M{i}", "email": f"a{i}@u.br", "categoria": "graduacao"}).json()["id"]
        m_id = client.post("/matriculas/solicitar", json={"aluno_id": a_id, "turma_id": turma_id}).json()["id"]
        matriculas_ids.append(m_id)

    # Finaliza o período de matrícula da turma
    r_fim = client.post(f"/turmas/{turma_id}/finalizar-periodo-matricula")
    assert r_fim.status_code == 200
    assert r_fim.json()["estado"] == "cancelada"

    # Todas as matrículas da turma devem ter passado ao estado cancelada
    for mid in matriculas_ids:
        m_check = client.get(f"/matriculas/{mid}").json()
        assert m_check["estado"] == "cancelada"


def test_regra5_turma_com_5_ou_mais_matriculas_mantida(client):
    r_disc = client.post("/disciplinas", json={"codigo": "DCC800", "nome": "Sistemas Operacionais", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"})
    disc_id = r_disc.json()["id"]

    r_turma = client.post("/turmas", json={"disciplina_id": disc_id, "semestre": "2026.1", "professor": "Tanenbaum", "numero_vagas": 20, "horario": "SEG 14:00-16:00"})
    turma_id = r_turma.json()["id"]

    # Matricula 5 alunos (>= 5)
    matriculas_ids = []
    for i in range(5):
        a_id = client.post("/alunos", json={"nome": f"Aluno SO {i}", "matricula": f"MSO{i}", "email": f"so{i}@u.br", "categoria": "graduacao"}).json()["id"]
        m_id = client.post("/matriculas/solicitar", json={"aluno_id": a_id, "turma_id": turma_id}).json()["id"]
        matriculas_ids.append(m_id)

    # Finaliza o período de matrícula da turma
    r_fim = client.post(f"/turmas/{turma_id}/finalizar-periodo-matricula")
    assert r_fim.status_code == 200
    assert r_fim.json()["estado"] != "cancelada"

    # As matrículas continuam confirmadas
    for mid in matriculas_ids:
        m_check = client.get(f"/matriculas/{mid}").json()
        assert m_check["estado"] == "confirmada"
