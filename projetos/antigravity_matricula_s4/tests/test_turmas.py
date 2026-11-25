import pytest


def test_criar_turma_sucesso(client):
    d = client.post("/disciplinas", json={
        "codigo": "INF101",
        "nome": "Introducao a Computacao",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Informatica"
    }).json()

    res = client.post("/turmas", json={
        "disciplina_id": d["id"],
        "semestre": "2026.1",
        "professor": "Alan Turing",
        "numero_vagas": 30,
        "horario": "SEG 08:00-10:00, QUA 08:00-10:00"
    })
    assert res.status_code == 201
    data = res.json()
    assert data["professor"] == "Alan Turing"
    assert data["numero_vagas"] == 30
    assert data["vagas_ocupadas"] == 0
    assert data["vagas_disponiveis"] == 30
    assert data["estado"] == "aberta"


def test_criar_turma_horario_invalido(client):
    d = client.post("/disciplinas", json={
        "codigo": "INF102",
        "nome": "Algoritmos",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Informatica"
    }).json()

    # Formato inválido
    res1 = client.post("/turmas", json={
        "disciplina_id": d["id"],
        "semestre": "2026.1",
        "professor": "Alan Turing",
        "numero_vagas": 30,
        "horario": "SEGUNDA 8h as 10h"
    })
    assert res1.status_code == 422

    # Horário de início posterior ao fim
    res2 = client.post("/turmas", json={
        "disciplina_id": d["id"],
        "semestre": "2026.1",
        "professor": "Alan Turing",
        "numero_vagas": 30,
        "horario": "SEG 10:00-08:00"
    })
    assert res2.status_code == 422


def test_regra_5_cancelamento_turma_menos_5_confirmadas(client):
    """
    Regra 5: Turma com menos de 5 matriculas confirmadas ao fim do periodo de matricula
    e cancelada, e todas as suas matriculas passam ao estado cancelada.
    """
    d = client.post("/disciplinas", json={
        "codigo": "FIS101",
        "nome": "Fisica 1",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Fisica"
    }).json()

    t = client.post("/turmas", json={
        "disciplina_id": d["id"],
        "semestre": "2026.1",
        "professor": "Isaac Newton",
        "numero_vagas": 20,
        "horario": "TER 10:00-12:00, QUI 10:00-12:00"
    }).json()

    # Matricular apenas 3 alunos (menos que 5)
    matriculas = []
    for i in range(1, 4):
        aluno = client.post("/alunos", json={
            "nome": f"Aluno {i}",
            "matricula": f"20260{i}",
            "email": f"aluno{i}@univ.br",
            "categoria": "graduacao",
            "situacao": "ativo"
        }).json()
        mat = client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": t["id"]}).json()
        assert mat["estado"] == "confirmada"
        matriculas.append(mat)

    # Encerrar período de matrícula para a turma
    res_encerra = client.post(f"/turmas/{t['id']}/encerrar-periodo")
    assert res_encerra.status_code == 200
    assert res_encerra.json()["estado"] == "cancelada"

    # Verificar se todas as suas matrículas passaram para cancelada
    for mat in matriculas:
        get_mat = client.get(f"/matriculas/{mat['id']}")
        assert get_mat.json()["estado"] == "cancelada"


def test_regra_5_turma_com_5_ou_mais_mantem_aberta(client):
    d = client.post("/disciplinas", json={
        "codigo": "FIS102",
        "nome": "Fisica 2",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Fisica"
    }).json()

    t = client.post("/turmas", json={
        "disciplina_id": d["id"],
        "semestre": "2026.1",
        "professor": "Isaac Newton",
        "numero_vagas": 20,
        "horario": "SEG 14:00-16:00, QUA 14:00-16:00"
    }).json()

    # Matricular exatamente 5 alunos
    for i in range(10, 15):
        aluno = client.post("/alunos", json={
            "nome": f"Aluno {i}",
            "matricula": f"20260{i}",
            "email": f"aluno{i}@univ.br",
            "categoria": "graduacao",
            "situacao": "ativo"
        }).json()
        mat = client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": t["id"]}).json()
        assert mat["estado"] == "confirmada"

    res_encerra = client.post(f"/turmas/{t['id']}/encerrar-periodo")
    assert res_encerra.status_code == 200
    assert res_encerra.json()["estado"] == "aberta"
