"""Testes unitários e de integração para os 3 relatórios gerenciais da API."""

import pytest


def test_relatorio_disciplinas_mais_procuradas(client):
    d1 = client.post("/disciplinas", json={"codigo": "D1", "nome": "IA", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    d2 = client.post("/disciplinas", json={"codigo": "D2", "nome": "Redes", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]

    t1 = client.post("/turmas", json={"disciplina_id": d1, "semestre": "2026.1", "professor": "P1", "numero_vagas": 10, "horario": "SEG 08:00-10:00"}).json()["id"]
    t2 = client.post("/turmas", json={"disciplina_id": d2, "semestre": "2026.1", "professor": "P2", "numero_vagas": 10, "horario": "TER 08:00-10:00"}).json()["id"]

    # 3 alunos na turma 1 (IA)
    for i in range(3):
        a = client.post("/alunos", json={"nome": f"A_IA_{i}", "matricula": f"IA_{i}", "email": f"ia_{i}@u.br", "categoria": "graduacao"}).json()["id"]
        client.post("/matriculas/solicitar", json={"aluno_id": a, "turma_id": t1})

    # 1 aluno na turma 2 (Redes)
    a_redes = client.post("/alunos", json={"nome": "A_Redes", "matricula": "RED1", "email": "red@u.br", "categoria": "graduacao"}).json()["id"]
    client.post("/matriculas/solicitar", json={"aluno_id": a_redes, "turma_id": t2})

    # Consulta relatório
    r = client.get("/relatorios/disciplinas-mais-procuradas?semestre=2026.1")
    assert r.status_code == 200
    rel = r.json()
    assert len(rel) == 2
    # IA deve ser a primeira (3 solicitações vs 1)
    assert rel[0]["codigo"] == "D1"
    assert rel[0]["total_solicitacoes"] == 3
    assert rel[1]["codigo"] == "D2"
    assert rel[1]["total_solicitacoes"] == 1


def test_relatorio_taxa_reprovacao(client):
    d1 = client.post("/disciplinas", json={"codigo": "CALC", "nome": "Cálculo", "numero_creditos": 4, "carga_horaria": 60, "departamento": "MAT"}).json()["id"]
    d2 = client.post("/disciplinas", json={"codigo": "PROG", "nome": "Programação", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]

    a1 = client.post("/alunos", json={"nome": "A1", "matricula": "M1", "email": "a1@u.br", "categoria": "graduacao"}).json()["id"]
    a2 = client.post("/alunos", json={"nome": "A2", "matricula": "M2", "email": "a2@u.br", "categoria": "graduacao"}).json()["id"]

    # Em CALC: 1 aprovado, 1 reprovado -> taxa 50%
    client.post("/historico", json={"aluno_id": a1, "disciplina_id": d1, "semestre": "2025.1", "nota": 7.0, "situacao": "aprovado"})
    client.post("/historico", json={"aluno_id": a2, "disciplina_id": d1, "semestre": "2025.1", "nota": 3.0, "situacao": "reprovado"})

    # Em PROG: 2 aprovados -> taxa 0%
    client.post("/historico", json={"aluno_id": a1, "disciplina_id": d2, "semestre": "2025.1", "nota": 9.0, "situacao": "aprovado"})
    client.post("/historico", json={"aluno_id": a2, "disciplina_id": d2, "semestre": "2025.1", "nota": 8.5, "situacao": "aprovado"})

    r = client.get("/relatorios/taxa-reprovacao")
    assert r.status_code == 200
    rel = r.json()

    calc_item = next(item for item in rel if item["codigo"] == "CALC")
    prog_item = next(item for item in rel if item["codigo"] == "PROG")

    assert calc_item["total_avaliados"] == 2
    assert calc_item["total_reprovados"] == 1
    assert calc_item["taxa_reprovacao_percentual"] == 50.0

    assert prog_item["total_avaliados"] == 2
    assert prog_item["total_reprovados"] == 0
    assert prog_item["taxa_reprovacao_percentual"] == 0.0


def test_relatorio_ocupacao_departamentos(client):
    d_dcc = client.post("/disciplinas", json={"codigo": "DCC01", "nome": "Algoritmos", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    d_mat = client.post("/disciplinas", json={"codigo": "MAT01", "nome": "Álgebra", "numero_creditos": 4, "carga_horaria": 60, "departamento": "MAT"}).json()["id"]

    # DCC: turma com 10 vagas, 2 ocupadas -> 20%
    t_dcc = client.post("/turmas", json={"disciplina_id": d_dcc, "semestre": "2026.1", "professor": "Prof DCC", "numero_vagas": 10, "horario": "SEG 08:00-10:00"}).json()["id"]
    # MAT: turma com 20 vagas, 1 ocupada -> 5%
    t_mat = client.post("/turmas", json={"disciplina_id": d_mat, "semestre": "2026.1", "professor": "Prof MAT", "numero_vagas": 20, "horario": "TER 08:00-10:00"}).json()["id"]

    a1 = client.post("/alunos", json={"nome": "A1", "matricula": "M1", "email": "a1@u.br", "categoria": "graduacao"}).json()["id"]
    a2 = client.post("/alunos", json={"nome": "A2", "matricula": "M2", "email": "a2@u.br", "categoria": "graduacao"}).json()["id"]

    # 2 matrículas em DCC
    client.post("/matriculas/solicitar", json={"aluno_id": a1, "turma_id": t_dcc})
    client.post("/matriculas/solicitar", json={"aluno_id": a2, "turma_id": t_dcc})

    # 1 matrícula em MAT
    client.post("/matriculas/solicitar", json={"aluno_id": a1, "turma_id": t_mat})

    r = client.get("/relatorios/ocupacao-departamentos?semestre=2026.1")
    assert r.status_code == 200
    rel = r.json()

    dcc_rep = next(item for item in rel if item["departamento"] == "DCC")
    mat_rep = next(item for item in rel if item["departamento"] == "MAT")

    assert dcc_rep["vagas_totais"] == 10
    assert dcc_rep["vagas_ocupadas"] == 2
    assert dcc_rep["taxa_ocupacao_geral_percentual"] == 20.0

    assert mat_rep["vagas_totais"] == 20
    assert mat_rep["vagas_ocupadas"] == 1
    assert mat_rep["taxa_ocupacao_geral_percentual"] == 5.0
