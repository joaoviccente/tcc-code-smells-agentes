from datetime import datetime, timezone, timedelta
import pytest

def test_limites_creditos_todas_categorias(client):
    # 1. Graduação: max 28 créditos
    aluno_grad = client.post("/alunos", json={"nome": "Grad", "matricula": "G28", "email": "g28@u.br", "categoria": "graduacao"}).json()["id"]

    # Criar 7 disciplinas de 4 créditos (7 * 4 = 28 créditos)
    turmas_grad = []
    for i in range(8):
        d = client.post("/disciplinas", json={"codigo": f"DG_{i}", "nome": f"DG {i}", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
        t = client.post("/turmas", json={"disciplina_id": d, "semestre": "2026.1", "professor": "P", "numero_vagas": 10, "horario": f"SEG {i}:00-{i+1}:00"}).json()["id"]
        turmas_grad.append(t)

    # 7 matrículas = 28 créditos (deve permitir)
    for i in range(7):
        res = client.post("/matriculas", json={"aluno_id": aluno_grad, "turma_id": turmas_grad[i]})
        assert res.status_code == 201

    # 8ª matrícula = 32 créditos (> 28 créditos) -> Deve rejeitar
    res_bloq_grad = client.post("/matriculas", json={"aluno_id": aluno_grad, "turma_id": turmas_grad[7]})
    assert res_bloq_grad.status_code == 400
    assert "limite de créditos excedido" in res_bloq_grad.json()["detail"].lower()

    # 2. Pós: max 16 créditos
    aluno_pos = client.post("/alunos", json={"nome": "Pos", "matricula": "P16", "email": "p16@u.br", "categoria": "pos"}).json()["id"]
    turmas_pos = []
    for i in range(5):
        d = client.post("/disciplinas", json={"codigo": f"DP_{i}", "nome": f"DP {i}", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
        t = client.post("/turmas", json={"disciplina_id": d, "semestre": "2026.1", "professor": "P", "numero_vagas": 10, "horario": f"TER {i}:00-{i+1}:00"}).json()["id"]
        turmas_pos.append(t)

    # 4 matrículas = 16 créditos (deve permitir)
    for i in range(4):
        res = client.post("/matriculas", json={"aluno_id": aluno_pos, "turma_id": turmas_pos[i]})
        assert res.status_code == 201

    # 5ª matrícula = 20 créditos (> 16 créditos) -> Deve rejeitar
    res_bloq_pos = client.post("/matriculas", json={"aluno_id": aluno_pos, "turma_id": turmas_pos[4]})
    assert res_bloq_pos.status_code == 400
    assert "limite de créditos excedido" in res_bloq_pos.json()["detail"].lower()

    # 3. Especial: max 8 créditos
    aluno_esp = client.post("/alunos", json={"nome": "Esp", "matricula": "E8", "email": "e8@u.br", "categoria": "especial"}).json()["id"]
    turmas_esp = []
    for i in range(3):
        d = client.post("/disciplinas", json={"codigo": f"DE_{i}", "nome": f"DE {i}", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
        t = client.post("/turmas", json={"disciplina_id": d, "semestre": "2026.1", "professor": "P", "numero_vagas": 10, "horario": f"QUA {i}:00-{i+1}:00"}).json()["id"]
        turmas_esp.append(t)

    # 2 matrículas = 8 créditos (deve permitir)
    for i in range(2):
        res = client.post("/matriculas", json={"aluno_id": aluno_esp, "turma_id": turmas_esp[i]})
        assert res.status_code == 201

    # 3ª matrícula = 12 créditos (> 8 créditos) -> Deve rejeitar
    res_bloq_esp = client.post("/matriculas", json={"aluno_id": aluno_esp, "turma_id": turmas_esp[2]})
    assert res_bloq_esp.status_code == 400
    assert "limite de créditos excedido" in res_bloq_esp.json()["detail"].lower()

def test_limite_trancamentos_por_disciplina(client):
    # Graduação: até 2 trancamentos por disciplina
    aluno_grad = client.post("/alunos", json={"nome": "G Tranca", "matricula": "G_TR2", "email": "gtr2@u.br", "categoria": "graduacao"}).json()["id"]
    d_grad = client.post("/disciplinas", json={"codigo": "D_GTR", "nome": "D GTR", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]

    # 1º semestre
    t1 = client.post("/turmas", json={"disciplina_id": d_grad, "semestre": "2025.1", "professor": "P", "numero_vagas": 10, "horario": "SEG 08:00-10:00"}).json()["id"]
    m1 = client.post("/matriculas", json={"aluno_id": aluno_grad, "turma_id": t1}).json()["id"]
    # Trancamento 1
    tr1 = client.post(f"/matriculas/{m1}/trancar")
    assert tr1.status_code == 200

    # 2º semestre
    t2 = client.post("/turmas", json={"disciplina_id": d_grad, "semestre": "2025.2", "professor": "P", "numero_vagas": 10, "horario": "SEG 08:00-10:00"}).json()["id"]
    m2 = client.post("/matriculas", json={"aluno_id": aluno_grad, "turma_id": t2}).json()["id"]
    # Trancamento 2
    tr2 = client.post(f"/matriculas/{m2}/trancar")
    assert tr2.status_code == 200

    # 3º semestre: tenta trancar a 3ª vez -> Bloqueado!
    t3 = client.post("/turmas", json={"disciplina_id": d_grad, "semestre": "2026.1", "professor": "P", "numero_vagas": 10, "horario": "SEG 08:00-10:00"}).json()["id"]
    m3 = client.post("/matriculas", json={"aluno_id": aluno_grad, "turma_id": t3}).json()["id"]
    tr3 = client.post(f"/matriculas/{m3}/trancar")
    assert tr3.status_code == 400
    assert "limite de trancamentos para a disciplina excedido" in tr3.json()["detail"].lower()

    # Pós: apenas 1 trancamento por disciplina
    aluno_pos = client.post("/alunos", json={"nome": "P Tranca", "matricula": "P_TR1", "email": "ptr1@u.br", "categoria": "pos"}).json()["id"]
    d_pos = client.post("/disciplinas", json={"codigo": "D_PTR", "nome": "D PTR", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]

    tp1 = client.post("/turmas", json={"disciplina_id": d_pos, "semestre": "2025.1", "professor": "P", "numero_vagas": 10, "horario": "SEG 08:00-10:00"}).json()["id"]
    mp1 = client.post("/matriculas", json={"aluno_id": aluno_pos, "turma_id": tp1}).json()["id"]
    trp1 = client.post(f"/matriculas/{mp1}/trancar")
    assert trp1.status_code == 200

    # 2ª tentativa de trancamento para Pós na mesma disciplina -> Bloqueado!
    tp2 = client.post("/turmas", json={"disciplina_id": d_pos, "semestre": "2025.2", "professor": "P", "numero_vagas": 10, "horario": "SEG 08:00-10:00"}).json()["id"]
    mp2 = client.post("/matriculas", json={"aluno_id": aluno_pos, "turma_id": tp2}).json()["id"]
    trp2 = client.post(f"/matriculas/{mp2}/trancar")
    assert trp2.status_code == 400
    assert "limite de trancamentos para a disciplina excedido" in trp2.json()["detail"].lower()

def test_prazos_cancelamento_por_categoria(client):
    # Graduação: 15 dias
    ag = client.post("/alunos", json={"nome": "AG", "matricula": "AG", "email": "ag@u.br", "categoria": "graduacao"}).json()["id"]
    dg = client.post("/disciplinas", json={"codigo": "DG_PRAZO", "nome": "DG", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    tg = client.post("/turmas", json={"disciplina_id": dg, "semestre": "2026.1", "professor": "P", "numero_vagas": 10, "horario": "SEG 08:00-10:00"}).json()["id"]

    mg = client.post("/matriculas", json={"aluno_id": ag, "turma_id": tg}).json()["id"]
    # Cancelamento no dia 15 -> dentro do prazo (não gera histórico de reprovação)
    data_dia_15 = datetime.now(timezone.utc) + timedelta(days=15)
    cg15 = client.post(f"/matriculas/{mg}/cancelar", json={"data_referencia": data_dia_15.isoformat()})
    assert cg15.status_code == 200
    assert len(client.get(f"/alunos/{ag}/historico").json()) == 0

    # Pós: 30 dias
    ap = client.post("/alunos", json={"nome": "AP", "matricula": "AP", "email": "ap@u.br", "categoria": "pos"}).json()["id"]
    dp = client.post("/disciplinas", json={"codigo": "DP_PRAZO", "nome": "DP", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    tp = client.post("/turmas", json={"disciplina_id": dp, "semestre": "2026.1", "professor": "P", "numero_vagas": 10, "horario": "SEG 08:00-10:00"}).json()["id"]

    mp = client.post("/matriculas", json={"aluno_id": ap, "turma_id": tp}).json()["id"]
    # Cancelamento no dia 31 -> fora do prazo (gera histórico de reprovação por falta)
    data_dia_31 = datetime.now(timezone.utc) + timedelta(days=31)
    cp31 = client.post(f"/matriculas/{mp}/cancelar", json={"data_referencia": data_dia_31.isoformat()})
    assert cp31.status_code == 200
    hist_p = client.get(f"/alunos/{ap}/historico").json()
    assert len(hist_p) == 1
    assert hist_p[0]["situacao"] == "reprovado_por_falta"

    # Especial: 7 dias
    ae = client.post("/alunos", json={"nome": "AE", "matricula": "AE", "email": "ae@u.br", "categoria": "especial"}).json()["id"]
    de = client.post("/disciplinas", json={"codigo": "DE_PRAZO", "nome": "DE", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    te = client.post("/turmas", json={"disciplina_id": de, "semestre": "2026.1", "professor": "P", "numero_vagas": 10, "horario": "SEG 08:00-10:00"}).json()["id"]

    me = client.post("/matriculas", json={"aluno_id": ae, "turma_id": te}).json()["id"]
    # Cancelamento no dia 8 -> fora do prazo (gera histórico de reprovação por falta)
    data_dia_8 = datetime.now(timezone.utc) + timedelta(days=8)
    ce8 = client.post(f"/matriculas/{me}/cancelar", json={"data_referencia": data_dia_8.isoformat()})
    assert ce8.status_code == 200
    hist_e = client.get(f"/alunos/{ae}/historico").json()
    assert len(hist_e) == 1
    assert hist_e[0]["situacao"] == "reprovado_por_falta"

def test_desempate_fila_por_data(client):
    # Turma com 1 vaga
    d = client.post("/disciplinas", json={"codigo": "D_DES", "nome": "DD", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    t = client.post("/turmas", json={"disciplina_id": d, "semestre": "2026.1", "professor": "P", "numero_vagas": 1, "horario": "SEX 08:00-10:00"}).json()["id"]

    # Aluno titular
    at = client.post("/alunos", json={"nome": "Titular", "matricula": "TIT", "email": "tit@u.br", "categoria": "graduacao"}).json()["id"]
    client.post("/matriculas", json={"aluno_id": at, "turma_id": t})

    # Dois alunos da MESMA categoria (Graduação)
    g1 = client.post("/alunos", json={"nome": "G1", "matricula": "G1", "email": "g1@u.br", "categoria": "graduacao"}).json()["id"]
    g2 = client.post("/alunos", json={"nome": "G2", "matricula": "G2", "email": "g2@u.br", "categoria": "graduacao"}).json()["id"]

    # G1 solicita primeiro, G2 solicita depois
    m_g1 = client.post("/matriculas", json={"aluno_id": g1, "turma_id": t}).json()
    m_g2 = client.post("/matriculas", json={"aluno_id": g2, "turma_id": t}).json()

    fila = client.get(f"/turmas/{t}/fila").json()["fila"]
    assert len(fila) == 2
    # G1 deve ser posição 1 e G2 posição 2 (desempate por data mais antiga)
    assert fila[0]["aluno_id"] == g1
    assert fila[1]["aluno_id"] == g2
