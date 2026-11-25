def test_relatorios(client):
    # Setup de dados
    # Disciplina 1 - DCC
    d1 = client.post("/disciplinas", json={"codigo": "DCC01", "nome": "Algoritmos", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    t1 = client.post("/turmas", json={"disciplina_id": d1, "semestre": "2026.1", "professor": "P1", "numero_vagas": 5, "horario": "SEG 08:00-10:00"}).json()["id"]

    # Disciplina 2 - DMAT
    d2 = client.post("/disciplinas", json={"codigo": "MAT01", "nome": "Álgebra", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DMAT"}).json()["id"]
    t2 = client.post("/turmas", json={"disciplina_id": d2, "semestre": "2026.1", "professor": "P2", "numero_vagas": 10, "horario": "TER 08:00-10:00"}).json()["id"]

    # Alunos
    a1 = client.post("/alunos", json={"nome": "A1", "matricula": "M1", "email": "a1@u.br", "categoria": "graduacao"}).json()["id"]
    a2 = client.post("/alunos", json={"nome": "A2", "matricula": "M2", "email": "a2@u.br", "categoria": "graduacao"}).json()["id"]
    a3 = client.post("/alunos", json={"nome": "A3", "matricula": "M3", "email": "a3@u.br", "categoria": "graduacao"}).json()["id"]

    # Matrículas
    # DCC01 tem 3 alunos
    client.post("/matriculas", json={"aluno_id": a1, "turma_id": t1})
    client.post("/matriculas", json={"aluno_id": a2, "turma_id": t1})
    client.post("/matriculas", json={"aluno_id": a3, "turma_id": t1})

    # MAT01 tem 1 aluno
    client.post("/matriculas", json={"aluno_id": a1, "turma_id": t2})

    # Histórico para taxa de reprovação
    # MAT01: 1 aprovado, 1 reprovado -> 50% taxa de reprovação
    client.post("/historico", json={"aluno_id": a1, "disciplina_id": d2, "semestre": "2025.2", "nota": 9.0, "situacao": "aprovado"})
    client.post("/historico", json={"aluno_id": a2, "disciplina_id": d2, "semestre": "2025.2", "nota": 3.0, "situacao": "reprovado"})

    # 1. Relatório: Disciplinas mais procuradas
    res_proc = client.get("/relatorios/disciplinas-mais-procuradas?semestre=2026.1")
    assert res_proc.status_code == 200
    dados_proc = res_proc.json()
    assert len(dados_proc) >= 2
    # DCC01 teve 3 matrículas, MAT01 teve 1 matrícula
    assert dados_proc[0]["codigo"] == "DCC01"
    assert dados_proc[0]["total_solicitacoes"] == 3
    assert dados_proc[1]["codigo"] == "MAT01"
    assert dados_proc[1]["total_solicitacoes"] == 1

    # 2. Relatório: Taxa de reprovação
    res_rep = client.get("/relatorios/taxa-reprovacao")
    assert res_rep.status_code == 200
    dados_rep = res_rep.json()
    mat_rep = next(r for r in dados_rep if r["codigo"] == "MAT01")
    assert mat_rep["total_avaliados"] == 2
    assert mat_rep["total_aprovados"] == 1
    assert mat_rep["total_reprovados"] == 1
    assert mat_rep["taxa_reprovacao_percentual"] == 50.0

    # 3. Relatório: Ocupação por departamento
    res_ocup = client.get("/relatorios/ocupacao-departamentos?semestre=2026.1")
    assert res_ocup.status_code == 200
    dados_ocup = res_ocup.json()
    # DCC: 3 confirmadas em 5 vagas = 60%
    dcc_ocup = next(r for r in dados_ocup if r["departamento"] == "DCC")
    assert dcc_ocup["total_vagas"] == 5
    assert dcc_ocup["total_confirmadas"] == 3
    assert dcc_ocup["taxa_ocupacao_percentual"] == 60.0

    # MAT: 1 confirmada em 10 vagas = 10%
    mat_ocup = next(r for r in dados_ocup if r["departamento"] == "DMAT")
    assert mat_ocup["total_vagas"] == 10
    assert mat_ocup["total_confirmadas"] == 1
    assert mat_ocup["taxa_ocupacao_percentual"] == 10.0
