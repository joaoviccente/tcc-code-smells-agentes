from datetime import datetime, timezone, timedelta
import pytest

def test_regra_1_aluno_ativo(client):
    # Criar aluno jubilado
    res_a = client.post("/alunos", json={
        "nome": "Aluno Jubilado",
        "matricula": "JUB01",
        "email": "jub@uni.edu",
        "categoria": "graduacao",
        "situacao": "jubilado"
    })
    aluno_id = res_a.json()["id"]

    # Criar disciplina e turma
    res_d = client.post("/disciplinas", json={
        "codigo": "MAT10",
        "nome": "Matemática Básica",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "DMAT"
    })
    disc_id = res_d.json()["id"]

    res_t = client.post("/turmas", json={
        "disciplina_id": disc_id,
        "semestre": "2026.1",
        "professor": "Prof. Euler",
        "numero_vagas": 20,
        "horario": "SEG 08:00-10:00"
    })
    turma_id = res_t.json()["id"]

    # Tentativa de matrícula deve falhar com 400
    res_mat = client.post("/matriculas", json={"aluno_id": aluno_id, "turma_id": turma_id})
    assert res_mat.status_code == 400
    assert "apenas alunos ativos" in res_mat.json()["detail"].lower()

def test_regra_1_pre_requisitos(client):
    # Criar Cálculo 1 e Cálculo 2
    res_c1 = client.post("/disciplinas", json={
        "codigo": "CALC1",
        "nome": "Cálculo 1",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "DMAT"
    })
    c1_id = res_c1.json()["id"]

    res_c2 = client.post("/disciplinas", json={
        "codigo": "CALC2",
        "nome": "Cálculo 2",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "DMAT",
        "pre_requisito_ids": [c1_id]
    })
    c2_id = res_c2.json()["id"]

    # Aluno ativo
    res_a = client.post("/alunos", json={
        "nome": "Aluno Teste",
        "matricula": "MAT_REQ",
        "email": "req@uni.edu",
        "categoria": "graduacao",
        "situacao": "ativo"
    })
    aluno_id = res_a.json()["id"]

    # Turma de Cálculo 2
    res_t = client.post("/turmas", json={
        "disciplina_id": c2_id,
        "semestre": "2026.1",
        "professor": "Prof. Newton",
        "numero_vagas": 20,
        "horario": "SEG 08:00-10:00"
    })
    turma_c2 = res_t.json()["id"]

    # Tenta matricular em Cálculo 2 sem ter cursado Cálculo 1 -> Falha 400
    res_fail = client.post("/matriculas", json={"aluno_id": aluno_id, "turma_id": turma_c2})
    assert res_fail.status_code == 400
    assert "pré-requisito não cumprido" in res_fail.json()["detail"].lower()

    # Adiciona aprovação em Cálculo 1 no histórico
    client.post("/historico", json={
        "aluno_id": aluno_id,
        "disciplina_id": c1_id,
        "semestre": "2025.2",
        "nota": 8.5,
        "situacao": "aprovado"
    })

    # Agora a matrícula em Cálculo 2 deve ter sucesso
    res_ok = client.post("/matriculas", json={"aluno_id": aluno_id, "turma_id": turma_c2})
    assert res_ok.status_code == 201
    assert res_ok.json()["estado"] == "confirmada"

def test_regra_1_limite_creditos_por_categoria(client):
    # Especial: max 8 créditos
    res_esp = client.post("/alunos", json={
        "nome": "Aluno Especial",
        "matricula": "ESP01",
        "email": "esp@uni.edu",
        "categoria": "especial",
        "situacao": "ativo"
    })
    esp_id = res_esp.json()["id"]

    # Disciplina 1 (6 créditos)
    d1 = client.post("/disciplinas", json={"codigo": "D6A", "nome": "D6A", "numero_creditos": 6, "carga_horaria": 90, "departamento": "DCC"}).json()["id"]
    t1 = client.post("/turmas", json={"disciplina_id": d1, "semestre": "2026.1", "professor": "P1", "numero_vagas": 10, "horario": "SEG 08:00-10:00"}).json()["id"]

    # Disciplina 2 (4 créditos)
    d2 = client.post("/disciplinas", json={"codigo": "D4B", "nome": "D4B", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    t2 = client.post("/turmas", json={"disciplina_id": d2, "semestre": "2026.1", "professor": "P2", "numero_vagas": 10, "horario": "TER 08:00-10:00"}).json()["id"]

    # Matrícula na turma 1 (6 créditos <= 8) -> OK
    m1 = client.post("/matriculas", json={"aluno_id": esp_id, "turma_id": t1})
    assert m1.status_code == 201

    # Matrícula na turma 2 (6 + 4 = 10 > 8) -> Falha 400 por limite de créditos
    m2 = client.post("/matriculas", json={"aluno_id": esp_id, "turma_id": t2})
    assert m2.status_code == 400
    assert "limite de créditos excedido" in m2.json()["detail"].lower()

def test_regra_3_reprovado_tres_vezes(client):
    # Aluno
    res_a = client.post("/alunos", json={
        "nome": "Aluno Dificuldade",
        "matricula": "REP01",
        "email": "rep@uni.edu",
        "categoria": "graduacao",
        "situacao": "ativo"
    })
    aluno_id = res_a.json()["id"]

    # Disciplina
    d = client.post("/disciplinas", json={"codigo": "F1", "nome": "Física 1", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DFIS"}).json()["id"]
    t = client.post("/turmas", json={"disciplina_id": d, "semestre": "2026.1", "professor": "Prof. Einstein", "numero_vagas": 10, "horario": "SEG 08:00-10:00"}).json()["id"]

    # Insere 2 reprovações
    for sem in ["2024.1", "2024.2"]:
        client.post("/historico", json={"aluno_id": aluno_id, "disciplina_id": d, "semestre": sem, "nota": 3.0, "situacao": "reprovado"})

    # Com 2 reprovações ainda consegue se matricular
    m1 = client.post("/matriculas", json={"aluno_id": aluno_id, "turma_id": t})
    assert m1.status_code == 201

    # Cancela para testar com 3 reprovações
    client.post(f"/matriculas/{m1.json()['id']}/cancelar")

    # Insere a 3ª reprovação
    client.post("/historico", json={"aluno_id": aluno_id, "disciplina_id": d, "semestre": "2025.1", "nota": 2.0, "situacao": "reprovado"})

    # Agora a nova matrícula deve ser negada
    m_bloq = client.post("/matriculas", json={"aluno_id": aluno_id, "turma_id": t})
    assert m_bloq.status_code == 400
    assert "reprovado 3 vezes" in m_bloq.json()["detail"].lower()

def test_regra_6_conflito_de_horarios(client):
    aluno_id = client.post("/alunos", json={
        "nome": "Aluno Tempo",
        "matricula": "CONF01",
        "email": "conf@uni.edu",
        "categoria": "graduacao",
        "situacao": "ativo"
    }).json()["id"]

    d1 = client.post("/disciplinas", json={"codigo": "D_CONF1", "nome": "D1", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    d2 = client.post("/disciplinas", json={"codigo": "D_CONF2", "nome": "D2", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]

    # Turma 1: SEG 08:00-10:00
    t1 = client.post("/turmas", json={"disciplina_id": d1, "semestre": "2026.1", "professor": "P1", "numero_vagas": 10, "horario": "SEG 08:00-10:00"}).json()["id"]
    # Turma 2: SEG 09:00-11:00 (conflita com T1!)
    t2 = client.post("/turmas", json={"disciplina_id": d2, "semestre": "2026.1", "professor": "P2", "numero_vagas": 10, "horario": "SEG 09:00-11:00"}).json()["id"]

    # Matrícula na primeira turma: OK
    res1 = client.post("/matriculas", json={"aluno_id": aluno_id, "turma_id": t1})
    assert res1.status_code == 201

    # Matrícula na segunda turma deve ser negada por conflito de horário (HTTP 409)
    res2 = client.post("/matriculas", json={"aluno_id": aluno_id, "turma_id": t2})
    assert res2.status_code == 409
    assert "conflito de horário" in res2.json()["detail"].lower()

def test_regra_2_lista_espera_prioridade_e_48h(client):
    # Turma com apenas 1 vaga
    d = client.post("/disciplinas", json={"codigo": "SO1", "nome": "Sistemas Operacionais", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    t = client.post("/turmas", json={"disciplina_id": d, "semestre": "2026.1", "professor": "Prof. Tanenbaum", "numero_vagas": 1, "horario": "SEG 14:00-16:00"}).json()["id"]

    # Aluno 1: Graduação (ocupa a vaga)
    a1 = client.post("/alunos", json={"nome": "A1 Grad", "matricula": "A1", "email": "a1@u.br", "categoria": "graduacao"}).json()["id"]
    # Aluno 2: Especial (entra na fila primeiro)
    a2 = client.post("/alunos", json={"nome": "A2 Esp", "matricula": "A2", "email": "a2@u.br", "categoria": "especial"}).json()["id"]
    # Aluno 3: Pós (solicita depois, mas tem prioridade alta!)
    a3 = client.post("/alunos", json={"nome": "A3 Pos", "matricula": "A3", "email": "a3@u.br", "categoria": "pos"}).json()["id"]

    # Matrícula A1 -> Confirmada
    m1 = client.post("/matriculas", json={"aluno_id": a1, "turma_id": t}).json()
    assert m1["estado"] == "confirmada"

    # Matrícula A2 (Especial) -> Lista de espera
    m2 = client.post("/matriculas", json={"aluno_id": a2, "turma_id": t}).json()
    assert m2["estado"] == "lista_de_espera"

    # Matrícula A3 (Pós) -> Lista de espera
    m3 = client.post("/matriculas", json={"aluno_id": a3, "turma_id": t}).json()
    assert m3["estado"] == "lista_de_espera"

    # Consulta a fila da turma: A3 (Pós, prioridade 3) deve estar na frente de A2 (Especial, prioridade 1)!
    fila_res = client.get(f"/turmas/{t}/fila").json()
    assert fila_res["total_na_fila"] == 2
    assert fila_res["fila"][0]["aluno_id"] == a3  # Pós está em 1º lugar
    assert fila_res["fila"][1]["aluno_id"] == a2  # Especial está em 2º lugar

    # Agora A1 cancela sua matrícula, liberando a vaga!
    client.post(f"/matriculas/{m1['id']}/cancelar")

    # A3 (primeiro da fila) foi promovido para 'solicitada' e tem 48h para confirmar
    m3_info = client.get(f"/matriculas/{m3['id']}").json()
    assert m3_info["estado"] == "solicitada"
    assert m3_info["data_limite_confirmacao"] is not None

    # Simula expiração de 48 horas (ex: 49 horas depois)
    futuro = datetime.now(timezone.utc) + timedelta(hours=49)
    # Tenta confirmar após o prazo de 48h -> Matrícula é cancelada e a vez passa para A2!
    conf_tardia = client.post(f"/matriculas/{m3['id']}/confirmar", json={"data_referencia": futuro.isoformat()})
    assert conf_tardia.status_code == 400

    # Verifica se m3 foi cancelada e se A2 foi promovido e agora tem 48h
    m3_final = client.get(f"/matriculas/{m3['id']}").json()
    assert m3_final["estado"] == "cancelada"

    m2_info = client.get(f"/matriculas/{m2['id']}").json()
    assert m2_info["estado"] == "solicitada"
    assert m2_info["data_limite_confirmacao"] is not None

    # A2 confirma dentro do seu prazo -> Matrícula Confirmada!
    dentro_prazo = futuro + timedelta(hours=10)
    conf_ok = client.post(f"/matriculas/{m2['id']}/confirmar", json={"data_referencia": dentro_prazo.isoformat()})
    assert conf_ok.status_code == 200
    assert conf_ok.json()["estado"] == "confirmada"

def test_regra_4_trancamento_e_cancelamento_fora_do_prazo(client):
    # Especial: 0 trancamentos permitidos
    esp = client.post("/alunos", json={"nome": "Esp Tranca", "matricula": "E_TR", "email": "etr@u.br", "categoria": "especial"}).json()["id"]
    # Graduação: 2 trancamentos, prazo 15 dias
    grad = client.post("/alunos", json={"nome": "Grad Tranca", "matricula": "G_TR", "email": "gtr@u.br", "categoria": "graduacao"}).json()["id"]

    d = client.post("/disciplinas", json={"codigo": "DISC_TR", "nome": "DTR", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    t = client.post("/turmas", json={"disciplina_id": d, "semestre": "2026.1", "professor": "P", "numero_vagas": 10, "horario": "SEG 10:00-12:00"}).json()["id"]

    # Especial tenta trancar: deve falhar porque o limite da categoria especial é 0!
    m_esp = client.post("/matriculas", json={"aluno_id": esp, "turma_id": t}).json()["id"]
    tranca_esp = client.post(f"/matriculas/{m_esp}/trancar")
    assert tranca_esp.status_code == 400
    assert "limite de trancamentos" in tranca_esp.json()["detail"].lower()

    # Graduação: matricular
    m_grad = client.post("/matriculas", json={"aluno_id": grad, "turma_id": t}).json()["id"]

    # Trancamento fora do prazo (ex: 20 dias depois; limite graduação é 15 dias) -> Falha 400
    data_tardia = datetime.now(timezone.utc) + timedelta(days=20)
    tranca_tardia = client.post(f"/matriculas/{m_grad}/trancar", json={"data_referencia": data_tardia.isoformat()})
    assert tranca_tardia.status_code == 400
    assert "prazo para trancamento expirado" in tranca_tardia.json()["detail"].lower()

    # Cancelamento fora do prazo (20 dias depois): cancela e registra "reprovação por falta" no histórico
    cancela_tardia = client.post(f"/matriculas/{m_grad}/cancelar", json={"data_referencia": data_tardia.isoformat()})
    assert cancela_tardia.status_code == 200
    assert cancela_tardia.json()["estado"] == "cancelada"

    # Verifica histórico do aluno: deve ter registro de reprovação por falta
    hist = client.get(f"/alunos/{grad}/historico").json()
    assert len(hist) == 1
    assert hist[0]["situacao"] == "reprovado_por_falta"

def test_regra_5_fim_periodo_matricula_menos_de_5(client):
    d = client.post("/disciplinas", json={"codigo": "D_POUCOS", "nome": "Poucos Alunos", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    t = client.post("/turmas", json={"disciplina_id": d, "semestre": "2026.1", "professor": "P", "numero_vagas": 20, "horario": "QUA 10:00-12:00"}).json()["id"]

    # Matricula 3 alunos (menos de 5)
    for i in range(3):
        a = client.post("/alunos", json={"nome": f"Aluno {i}", "matricula": f"POUCO_{i}", "email": f"p{i}@u.br", "categoria": "graduacao"}).json()["id"]
        client.post("/matriculas", json={"aluno_id": a, "turma_id": t})

    # Fim do período de matrícula na turma
    res_fim = client.post(f"/turmas/{t}/finalizar-periodo-matricula")
    assert res_fim.status_code == 200
    assert res_fim.json()["estado"] == "cancelada"

    # Todas as matrículas da turma devem ter sido canceladas
    mats = client.get(f"/matriculas?turma_id={t}").json()
    assert len(mats) == 3
    for m in mats:
        assert m["estado"] == "cancelada"

def test_regra_7_tres_trancamentos_no_semestre(client):
    # Aluno que tranca 3 disciplinas no semestre passa à situação 'trancado' e tem demais confirmadas canceladas
    aluno_id = client.post("/alunos", json={"nome": "Aluno Trancador", "matricula": "T_ALL", "email": "tall@u.br", "categoria": "graduacao"}).json()["id"]

    # 4 disciplinas distintas
    turmas = []
    for i in range(4):
        d = client.post("/disciplinas", json={"codigo": f"D_T_{i}", "nome": f"Disc {i}", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
        t = client.post("/turmas", json={"disciplina_id": d, "semestre": "2026.1", "professor": "P", "numero_vagas": 10, "horario": f"SEG {8+i*2:02d}:00-{10+i*2:02d}:00"}).json()["id"]
        turmas.append(t)

    # Matricula nas 4 turmas (total 16 créditos <= 28)
    matriculas = []
    for t_id in turmas:
        m = client.post("/matriculas", json={"aluno_id": aluno_id, "turma_id": t_id}).json()["id"]
        matriculas.append(m)

    # Tranca 1ª disciplina dentro do prazo
    client.post(f"/matriculas/{matriculas[0]}/trancar")
    aluno = client.get(f"/alunos/{aluno_id}").json()
    assert aluno["situacao"] == "ativo"

    # Tranca 2ª disciplina
    client.post(f"/matriculas/{matriculas[1]}/trancar")
    aluno = client.get(f"/alunos/{aluno_id}").json()
    assert aluno["situacao"] == "ativo"

    # Tranca 3ª disciplina -> atinge 3 trancamentos no semestre!
    client.post(f"/matriculas/{matriculas[2]}/trancar")

    # Aluno agora deve estar com situacao 'trancado'
    aluno = client.get(f"/alunos/{aluno_id}").json()
    assert aluno["situacao"] == "trancado"

    # A 4ª matrícula (que estava confirmada) deve ter sido automaticamente cancelada!
    m4 = client.get(f"/matriculas/{matriculas[3]}").json()
    assert m4["estado"] == "cancelada"
