import pytest


def test_relatorio_disciplinas_mais_procuradas(client):
    d1 = client.post("/disciplinas", json={
        "codigo": "REL1",
        "nome": "Estruturas de Dados",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Computacao"
    }).json()

    d2 = client.post("/disciplinas", json={
        "codigo": "REL2",
        "nome": "Redes de Computadores",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Computacao"
    }).json()

    t1 = client.post("/turmas", json={
        "disciplina_id": d1["id"],
        "semestre": "2026.1",
        "professor": "Prof 1",
        "numero_vagas": 20,
        "horario": "SEG 08:00-10:00"
    }).json()

    t2 = client.post("/turmas", json={
        "disciplina_id": d2["id"],
        "semestre": "2026.1",
        "professor": "Prof 2",
        "numero_vagas": 20,
        "horario": "TER 08:00-10:00"
    }).json()

    # Criar alunos e matricular 2 em d1 e 1 em d2
    a1 = client.post("/alunos", json={
        "nome": "Aluno R1",
        "matricula": "R001",
        "email": "r1@univ.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }).json()
    a2 = client.post("/alunos", json={
        "nome": "Aluno R2",
        "matricula": "R002",
        "email": "r2@univ.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }).json()

    client.post("/matriculas", json={"aluno_id": a1["id"], "turma_id": t1["id"]})
    client.post("/matriculas", json={"aluno_id": a2["id"], "turma_id": t1["id"]})
    client.post("/matriculas", json={"aluno_id": a1["id"], "turma_id": t2["id"]})

    res = client.get("/relatorios/disciplinas-mais-procuradas?semestre=2026.1")
    assert res.status_code == 200
    data = res.json()["disciplinas"]
    assert len(data) >= 2
    # d1 deve ser a primeira por ter 2 solicitações contra 1 de d2
    assert data[0]["codigo"] == "REL1"
    assert data[0]["total_solicitacoes"] == 2
    assert data[1]["codigo"] == "REL2"
    assert data[1]["total_solicitacoes"] == 1


def test_relatorio_taxa_reprovacao(client):
    d = client.post("/disciplinas", json={
        "codigo": "TAXA1",
        "nome": "Estatistica",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Estatistica"
    }).json()

    aluno1 = client.post("/alunos", json={
        "nome": "Aluno T1",
        "matricula": "T001",
        "email": "t1@univ.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }).json()

    aluno2 = client.post("/alunos", json={
        "nome": "Aluno T2",
        "matricula": "T002",
        "email": "t2@univ.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }).json()

    # Aluno 1 aprovado
    client.post(f"/alunos/{aluno1['id']}/historico", json={
        "aluno_id": aluno1["id"],
        "disciplina_id": d["id"],
        "semestre": "2025.1",
        "nota": 8.0,
        "situacao": "aprovado"
    })

    # Aluno 2 reprovado
    client.post(f"/alunos/{aluno2['id']}/historico", json={
        "aluno_id": aluno2["id"],
        "disciplina_id": d["id"],
        "semestre": "2025.1",
        "nota": 3.0,
        "situacao": "reprovado"
    })

    res = client.get("/relatorios/taxa-reprovacao")
    assert res.status_code == 200
    lista = res.json()["disciplinas"]
    item = next(x for x in lista if x["codigo"] == "TAXA1")
    assert item["total_concluidos"] == 2
    assert item["total_aprovados"] == 1
    assert item["total_reprovados"] == 1
    assert item["taxa_reprovacao_percentual"] == 50.0


def test_relatorio_ocupacao_departamentos(client):
    d = client.post("/disciplinas", json={
        "codigo": "OCUP1",
        "nome": "Algoritmos Avancados",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Departamento de Computacao"
    }).json()

    # Turma com 10 vagas
    t = client.post("/turmas", json={
        "disciplina_id": d["id"],
        "semestre": "2026.1",
        "professor": "Prof Computacao",
        "numero_vagas": 10,
        "horario": "QUA 10:00-12:00"
    }).json()

    # Matricular 5 alunos
    for i in range(1, 6):
        a = client.post("/alunos", json={
            "nome": f"Aluno OC {i}",
            "matricula": f"OC00{i}",
            "email": f"oc{i}@univ.br",
            "categoria": "graduacao",
            "situacao": "ativo"
        }).json()
        client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": t["id"]})

    res = client.get("/relatorios/ocupacao-departamentos?semestre=2026.1")
    assert res.status_code == 200
    deptos = res.json()["departamentos"]
    dep = next(x for x in deptos if x["departamento"] == "Departamento de Computacao")
    assert dep["total_vagas"] == 10
    assert dep["vagas_ocupadas"] == 5
    assert dep["taxa_ocupacao_percentual"] == 50.0
