def test_relatorios(client):
    # Criar departamentos e disciplinas
    d1 = client.post("/disciplinas", json={
        "codigo": "REL_MAT1", "nome": "Cálculo I", "numero_creditos": 4, "carga_horaria": 60, "departamento": "Matemática"
    }).json()["id"]
    d2 = client.post("/disciplinas", json={
        "codigo": "REL_FIS1", "nome": "Física I", "numero_creditos": 4, "carga_horaria": 60, "departamento": "Física"
    }).json()["id"]

    # Criar turmas
    t1 = client.post("/turmas", json={
        "disciplina_id": d1, "semestre": "2026.1", "professor": "Prof Mat", "numero_vagas": 10, "horario": "SEG 08:00-10:00"
    }).json()["id"]
    t2 = client.post("/turmas", json={
        "disciplina_id": d2, "semestre": "2026.1", "professor": "Prof Fis", "numero_vagas": 10, "horario": "TER 08:00-10:00"
    }).json()["id"]

    # Alunos
    a1 = client.post("/alunos", json={"nome": "A1", "matricula": "M1", "e_mail": "m1@r.com", "categoria": "graduacao"}).json()["id"]
    a2 = client.post("/alunos", json={"nome": "A2", "matricula": "M2", "e_mail": "m2@r.com", "categoria": "graduacao"}).json()["id"]
    a3 = client.post("/alunos", json={"nome": "A3", "matricula": "M3", "e_mail": "m3@r.com", "categoria": "graduacao"}).json()["id"]

    # Matrículas: 2 em Cálculo, 1 em Física
    client.post("/matriculas/solicitar", json={"aluno_id": a1, "turma_id": t1})
    client.post("/matriculas/solicitar", json={"aluno_id": a2, "turma_id": t1})
    client.post("/matriculas/solicitar", json={"aluno_id": a3, "turma_id": t2})

    # Histórico para taxa de reprovação:
    # d1 (Cálculo): 1 aprovado, 1 reprovado (taxa 50%)
    client.post("/historico", json={"aluno_id": a1, "disciplina_id": d1, "semestre": "2025.2", "nota": 7.0, "situacao": "aprovado"})
    client.post("/historico", json={"aluno_id": a2, "disciplina_id": d1, "semestre": "2025.2", "nota": 3.0, "situacao": "reprovado"})
    # d2 (Física): 2 aprovados, 0 reprovados (taxa 0%)
    client.post("/historico", json={"aluno_id": a1, "disciplina_id": d2, "semestre": "2025.2", "nota": 9.0, "situacao": "aprovado"})
    client.post("/historico", json={"aluno_id": a2, "disciplina_id": d2, "semestre": "2025.2", "nota": 8.0, "situacao": "aprovado"})

    # 1. Teste Relatório Disciplinas Mais Procuradas
    res_proc = client.get("/relatorios/disciplinas-mais-procuradas?semestre=2026.1")
    assert res_proc.status_code == 200
    dados_proc = res_proc.json()["disciplinas"]
    assert len(dados_proc) >= 2
    # Cálculo deve ser o primeiro (2 solicitações vs 1 de física)
    assert dados_proc[0]["codigo"] == "REL_MAT1"
    assert dados_proc[0]["total_solicitacoes"] == 2

    # 2. Teste Relatório Taxa de Reprovação
    res_taxa = client.get("/relatorios/taxa-reprovacao")
    assert res_taxa.status_code == 200
    dados_taxa = res_taxa.json()["disciplinas"]
    calc_rep = next(d for d in dados_taxa if d["codigo"] == "REL_MAT1")
    assert calc_rep["taxa_reprovacao_percentual"] == 50.0

    # 3. Teste Relatório Ocupação Departamentos
    res_ocup = client.get("/relatorios/ocupacao-departamentos?semestre=2026.1")
    assert res_ocup.status_code == 200
    dados_ocup = res_ocup.json()["departamentos"]
    dept_mat = next(dep for dep in dados_ocup if dep["departamento"] == "Matemática")
    assert dept_mat["total_vagas_ofertadas"] == 10
    assert dept_mat["total_vagas_ocupadas"] == 2
    assert dept_mat["taxa_ocupacao_geral_percentual"] == 20.0
