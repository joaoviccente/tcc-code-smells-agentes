import pytest


def test_regra1_aluno_ativo_e_prerequisitos(client):
    # Cria disciplinas: Cálculo I e Cálculo II
    r_c1 = client.post("/disciplinas", json={"codigo": "MAT101", "nome": "Cálculo I", "numero_creditos": 4, "carga_horaria": 60, "departamento": "MAT"})
    r_c2 = client.post("/disciplinas", json={"codigo": "MAT102", "nome": "Cálculo II", "numero_creditos": 4, "carga_horaria": 60, "departamento": "MAT"})
    c1_id = r_c1.json()["id"]
    c2_id = r_c2.json()["id"]

    # MAT101 é pré-requisito de MAT102
    client.post(f"/disciplinas/{c2_id}/pre-requisitos", json={"prerequisito_id": c1_id})

    # Cria turmas
    r_t1 = client.post("/turmas", json={"disciplina_id": c1_id, "semestre": "2026.1", "professor": "Prof 1", "numero_vagas": 30, "horario": "SEG 08:00-10:00"})
    r_t2 = client.post("/turmas", json={"disciplina_id": c2_id, "semestre": "2026.1", "professor": "Prof 2", "numero_vagas": 30, "horario": "TER 08:00-10:00"})
    t1_id = r_t1.json()["id"]
    t2_id = r_t2.json()["id"]

    # Cria alunos
    r_aluno_ativo = client.post("/alunos", json={"nome": "Lucas Ativo", "matricula": "202601", "email": "lucas@u.br", "categoria": "graduacao", "situacao": "ativo"})
    r_aluno_tranc = client.post("/alunos", json={"nome": "Tiago Trancado", "matricula": "202602", "email": "tiago@u.br", "categoria": "graduacao", "situacao": "trancado"})
    r_aluno_jub = client.post("/alunos", json={"nome": "Paula Jubilada", "matricula": "202603", "email": "paula@u.br", "categoria": "graduacao", "situacao": "jubilado"})

    aluno_ativo_id = r_aluno_ativo.json()["id"]
    aluno_tranc_id = r_aluno_tranc.json()["id"]
    aluno_jub_id = r_aluno_jub.json()["id"]

    # 1. Aluno não ativo é negado
    r_neg1 = client.post("/matriculas/solicitar", json={"aluno_id": aluno_tranc_id, "turma_id": t1_id})
    assert r_neg1.status_code == 400
    assert "não está ativo" in r_neg1.json()["detail"]

    r_neg2 = client.post("/matriculas/solicitar", json={"aluno_id": aluno_jub_id, "turma_id": t1_id})
    assert r_neg2.status_code == 400
    assert "não está ativo" in r_neg2.json()["detail"]

    # 2. Aluno ativo sem pré-requisito de Cálculo II é negado
    r_neg_prereq = client.post("/matriculas/solicitar", json={"aluno_id": aluno_ativo_id, "turma_id": t2_id})
    assert r_neg_prereq.status_code == 400
    assert "pré-requisito não cumprido" in r_neg_prereq.json()["detail"].lower()

    # Registra aprovação em Cálculo I no Histórico
    client.post("/historico", json={"aluno_id": aluno_ativo_id, "disciplina_id": c1_id, "semestre": "2025.2", "nota": 8.5, "situacao": "aprovado"})

    # Agora deve conseguir se matricular em Cálculo II
    r_ok = client.post("/matriculas/solicitar", json={"aluno_id": aluno_ativo_id, "turma_id": t2_id})
    assert r_ok.status_code == 201
    assert r_ok.json()["estado"] == "confirmada"


def test_regra1_limite_de_creditos_por_categoria(client):
    # Graduação: máx 28 créditos
    # Pós: máx 16 créditos
    # Especial: máx 8 créditos

    # Cria aluno especial
    r_esp = client.post("/alunos", json={"nome": "Aluno Especial", "matricula": "ESP1", "email": "esp1@u.br", "categoria": "especial"})
    esp_id = r_esp.json()["id"]

    # Cria 3 disciplinas de 4 créditos cada
    d1 = client.post("/disciplinas", json={"codigo": "D1", "nome": "Disc 1", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    d2 = client.post("/disciplinas", json={"codigo": "D2", "nome": "Disc 2", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    d3 = client.post("/disciplinas", json={"codigo": "D3", "nome": "Disc 3", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]

    # Cria turmas em horários diferentes
    t1 = client.post("/turmas", json={"disciplina_id": d1, "semestre": "2026.1", "professor": "P1", "numero_vagas": 10, "horario": "SEG 08:00-10:00"}).json()["id"]
    t2 = client.post("/turmas", json={"disciplina_id": d2, "semestre": "2026.1", "professor": "P2", "numero_vagas": 10, "horario": "TER 08:00-10:00"}).json()["id"]
    t3 = client.post("/turmas", json={"disciplina_id": d3, "semestre": "2026.1", "professor": "P3", "numero_vagas": 10, "horario": "QUA 08:00-10:00"}).json()["id"]

    # Turma 1 (4 créditos) -> OK (total: 4)
    r1 = client.post("/matriculas/solicitar", json={"aluno_id": esp_id, "turma_id": t1})
    assert r1.status_code == 201

    # Turma 2 (4 créditos) -> OK (total: 8)
    r2 = client.post("/matriculas/solicitar", json={"aluno_id": esp_id, "turma_id": t2})
    assert r2.status_code == 201

    # Turma 3 (4 créditos) -> 8 + 4 = 12 > 8 (limite da especial) -> NEGADA!
    r3 = client.post("/matriculas/solicitar", json={"aluno_id": esp_id, "turma_id": t3})
    assert r3.status_code == 400
    assert "limite de créditos" in r3.json()["detail"].lower()


def test_regra3_aluno_reprovado_tres_vezes(client):
    # Aluno reprovado 3 vezes na mesma disciplina fica impedido de se matricular nela novamente
    r_aluno = client.post("/alunos", json={"nome": "João Repetiu", "matricula": "2026REP", "email": "rep@u.br", "categoria": "graduacao"})
    aluno_id = r_aluno.json()["id"]

    r_disc = client.post("/disciplinas", json={"codigo": "FIS101", "nome": "Física I", "numero_creditos": 4, "carga_horaria": 60, "departamento": "FIS"})
    disc_id = r_disc.json()["id"]

    r_turma = client.post("/turmas", json={"disciplina_id": disc_id, "semestre": "2026.1", "professor": "Prof Newton", "numero_vagas": 20, "horario": "SEG 10:00-12:00"})
    turma_id = r_turma.json()["id"]

    # 1ª reprovação
    client.post("/historico", json={"aluno_id": aluno_id, "disciplina_id": disc_id, "semestre": "2024.1", "nota": 3.0, "situacao": "reprovado"})
    # 2ª reprovação
    client.post("/historico", json={"aluno_id": aluno_id, "disciplina_id": disc_id, "semestre": "2024.2", "nota": 4.0, "situacao": "reprovado"})

    # Ainda pode se matricular com 2 reprovações
    # Vamos verificar se consegue solicitar (vamos limpar a matrícula depois)
    r_mat = client.post("/matriculas/solicitar", json={"aluno_id": aluno_id, "turma_id": turma_id})
    assert r_mat.status_code == 201
    # Cancela para liberar
    client.post(f"/matriculas/{r_mat.json()['id']}/cancelar")

    # 3ª reprovação (por falta)
    client.post("/historico", json={"aluno_id": aluno_id, "disciplina_id": disc_id, "semestre": "2025.1", "nota": 0.0, "situacao": "reprovado_por_falta"})

    # Agora tem 3 reprovações -> IMPEDIDO!
    r_bloq = client.post("/matriculas/solicitar", json={"aluno_id": aluno_id, "turma_id": turma_id})
    assert r_bloq.status_code == 400
    assert "reprovado 3 vezes" in r_bloq.json()["detail"].lower() or "máximo permitido" in r_bloq.json()["detail"].lower()


def test_regra6_conflito_de_horario(client):
    # Matrícula em turma cujo horário conflita com outra turma já confirmada do aluno é negada
    r_aluno = client.post("/alunos", json={"nome": "Sam", "matricula": "SAM1", "email": "sam@u.br", "categoria": "graduacao"})
    aluno_id = r_aluno.json()["id"]

    d1 = client.post("/disciplinas", json={"codigo": "A1", "nome": "Disc A", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    d2 = client.post("/disciplinas", json={"codigo": "B1", "nome": "Disc B", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]

    # Turma 1: SEG 08:00-10:00
    t1 = client.post("/turmas", json={"disciplina_id": d1, "semestre": "2026.1", "professor": "P1", "numero_vagas": 20, "horario": "SEG 08:00-10:00"}).json()["id"]
    # Turma 2: mesmo horário SEG 08:00-10:00
    t2 = client.post("/turmas", json={"disciplina_id": d2, "semestre": "2026.1", "professor": "P2", "numero_vagas": 20, "horario": "SEG 08:00-10:00"}).json()["id"]

    # Matricula na Turma 1 -> confirmada
    r1 = client.post("/matriculas/solicitar", json={"aluno_id": aluno_id, "turma_id": t1})
    assert r1.status_code == 201
    assert r1.json()["estado"] == "confirmada"

    # Tenta matricular na Turma 2 (conflito de horário) -> NEGADA!
    r2 = client.post("/matriculas/solicitar", json={"aluno_id": aluno_id, "turma_id": t2})
    assert r2.status_code == 400
    assert "conflito de horário" in r2.json()["detail"].lower()
