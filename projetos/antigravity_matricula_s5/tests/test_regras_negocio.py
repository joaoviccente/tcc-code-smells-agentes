from datetime import datetime, timezone, timedelta
import pytest

def test_regra_1_aluno_ativo(client):
    # Aluno trancado tentando se matricular
    res_disc = client.post("/disciplinas", json={
        "codigo": "MAT10", "nome": "Cálculo", "numero_creditos": 4, "carga_horaria": 60, "departamento": "Mat"
    })
    res_turma = client.post("/turmas", json={
        "disciplina_id": res_disc.json()["id"], "semestre": "2026.1", "professor": "Prof", "numero_vagas": 10, "horario": "SEG 08:00-10:00"
    })
    res_aluno = client.post("/alunos", json={
        "nome": "Aluno Trancado", "matricula": "T01", "e_mail": "t01@test.com", "categoria": "graduacao", "situacao": "trancado"
    })
    res_mat = client.post("/matriculas/solicitar", json={
        "aluno_id": res_aluno.json()["id"], "turma_id": res_turma.json()["id"]
    })
    assert res_mat.status_code == 400
    assert "ativo" in res_mat.json()["detail"].lower()


def test_regra_1_prerequisitos(client):
    # Criar Disc A e Disc B (exige A)
    res_a = client.post("/disciplinas", json={
        "codigo": "PRQ1", "nome": "Prog 1", "numero_creditos": 4, "carga_horaria": 60, "departamento": "TI"
    })
    res_b = client.post("/disciplinas", json={
        "codigo": "PRQ2", "nome": "Prog 2", "numero_creditos": 4, "carga_horaria": 60, "departamento": "TI",
        "prerequisitos_ids": [res_a.json()["id"]]
    })
    res_turma_b = client.post("/turmas", json={
        "disciplina_id": res_b.json()["id"], "semestre": "2026.1", "professor": "Prof", "numero_vagas": 10, "horario": "SEG 08:00-10:00"
    })
    res_aluno = client.post("/alunos", json={
        "nome": "Aluno Teste", "matricula": "PR01", "e_mail": "pr01@test.com", "categoria": "graduacao"
    })

    aluno_id = res_aluno.json()["id"]
    turma_b_id = res_turma_b.json()["id"]

    # Tentativa sem pré-requisito cumprido -> 400
    res_falha = client.post("/matriculas/solicitar", json={"aluno_id": aluno_id, "turma_id": turma_b_id})
    assert res_falha.status_code == 400
    assert "pré-requisito" in res_falha.json()["detail"].lower()

    # Inserir aprovação no histórico para Disc A
    client.post("/historico", json={
        "aluno_id": aluno_id,
        "disciplina_id": res_a.json()["id"],
        "semestre": "2025.2",
        "nota": 8.5,
        "situacao": "aprovado"
    })

    # Agora deve permitir matrícula
    res_sucesso = client.post("/matriculas/solicitar", json={"aluno_id": aluno_id, "turma_id": turma_b_id})
    assert res_sucesso.status_code == 201
    assert res_sucesso.json()["estado"] == "confirmada"


def test_regra_1_limite_creditos_por_categoria(client):
    # Graduação: máx 28; Pós: máx 16; Especial: máx 8
    # Disciplina 10 créditos
    d1 = client.post("/disciplinas", json={
        "codigo": "CR10", "nome": "Pesada 10cr", "numero_creditos": 10, "carga_horaria": 150, "departamento": "Geral"
    }).json()["id"]
    t1 = client.post("/turmas", json={
        "disciplina_id": d1, "semestre": "2026.1", "professor": "P1", "numero_vagas": 10, "horario": "SEG 08:00-10:00"
    }).json()["id"]

    # Aluno Especial (máx 8 créditos) tenta pegar turma de 10 créditos -> 400
    esp = client.post("/alunos", json={
        "nome": "Aluno Esp", "matricula": "ESP01", "e_mail": "esp01@test.com", "categoria": "especial"
    }).json()["id"]

    res_esp = client.post("/matriculas/solicitar", json={"aluno_id": esp, "turma_id": t1})
    assert res_esp.status_code == 400
    assert "créditos" in res_esp.json()["detail"].lower()

    # Aluno Pós (máx 16 créditos): pode pegar 10cr, mas se tentar outra de 10cr totalizando 20cr -> 400
    pos = client.post("/alunos", json={
        "nome": "Aluno Pos", "matricula": "POS01", "e_mail": "pos01@test.com", "categoria": "pos"
    }).json()["id"]
    d2 = client.post("/disciplinas", json={
        "codigo": "CR10B", "nome": "Pesada 10cr B", "numero_creditos": 10, "carga_horaria": 150, "departamento": "Geral"
    }).json()["id"]
    t2 = client.post("/turmas", json={
        "disciplina_id": d2, "semestre": "2026.1", "professor": "P2", "numero_vagas": 10, "horario": "TER 08:00-10:00"
    }).json()["id"]

    res_pos1 = client.post("/matriculas/solicitar", json={"aluno_id": pos, "turma_id": t1})
    assert res_pos1.status_code == 201

    res_pos2 = client.post("/matriculas/solicitar", json={"aluno_id": pos, "turma_id": t2})
    assert res_pos2.status_code == 400
    assert "créditos" in res_pos2.json()["detail"].lower()


def test_regra_2_lista_espera_prioridades_e_48h(client):
    # Turma com apenas 1 vaga
    disc = client.post("/disciplinas", json={
        "codigo": "LE01", "nome": "Topicos Especiais", "numero_creditos": 4, "carga_horaria": 60, "departamento": "TI"
    }).json()["id"]
    turma = client.post("/turmas", json={
        "disciplina_id": disc, "semestre": "2026.1", "professor": "Prof Fila", "numero_vagas": 1, "horario": "SEG 08:00-10:00"
    }).json()["id"]

    # Aluno 1 ocupa a única vaga
    aluno1 = client.post("/alunos", json={
        "nome": "A1 Grad", "matricula": "A1", "e_mail": "a1@test.com", "categoria": "graduacao"
    }).json()["id"]
    m1 = client.post("/matriculas/solicitar", json={"aluno_id": aluno1, "turma_id": turma}).json()
    assert m1["estado"] == "confirmada"

    # Alunos para lista de espera:
    # Especial entra primeiro no tempo t0
    aluno_esp = client.post("/alunos", json={
        "nome": "A Esp", "matricula": "AESP", "e_mail": "aesp@test.com", "categoria": "especial"
    }).json()["id"]
    m_esp = client.post("/matriculas/solicitar", json={"aluno_id": aluno_esp, "turma_id": turma}).json()
    assert m_esp["estado"] == "lista_de_espera"

    # Graduação entra depois no tempo t1
    aluno_grad = client.post("/alunos", json={
        "nome": "A Grad", "matricula": "AGRAD", "e_mail": "agrad@test.com", "categoria": "graduacao"
    }).json()["id"]
    m_grad = client.post("/matriculas/solicitar", json={"aluno_id": aluno_grad, "turma_id": turma}).json()
    assert m_grad["estado"] == "lista_de_espera"

    # Pós entra por último no tempo t2
    aluno_pos = client.post("/alunos", json={
        "nome": "A Pos", "matricula": "APOS", "e_mail": "apos@test.com", "categoria": "pos"
    }).json()["id"]
    m_pos = client.post("/matriculas/solicitar", json={"aluno_id": aluno_pos, "turma_id": turma}).json()
    assert m_pos["estado"] == "lista_de_espera"

    # Verificar ordem da fila de espera:
    # Prioridades: Pós (1 - alta) > Graduação (2 - média) > Especial (3 - baixa)
    res_fila = client.get(f"/turmas/{turma}/fila")
    assert res_fila.status_code == 200
    fila = res_fila.json()["fila"]
    assert len(fila) == 3
    assert fila[0]["aluno_id"] == aluno_pos   # Pos primeiro
    assert fila[1]["aluno_id"] == aluno_grad  # Graduacao segundo
    assert fila[2]["aluno_id"] == aluno_esp   # Especial terceiro

    # Agora o Aluno 1 cancela sua matrícula dentro do prazo
    res_canc = client.post(f"/matriculas/{m1['id']}/cancelar")
    assert res_canc.status_code == 200

    # A vaga é liberada para o primeiro da fila (Aluno Pós)!
    res_fila2 = client.get(f"/turmas/{turma}/fila")
    fila2 = res_fila2.json()["fila"]
    assert fila2[0]["aluno_id"] == aluno_pos
    assert fila2[0]["aguardando_confirmacao"] is True
    assert fila2[0]["limite_confirmacao_em"] is not None

    # Testar confirmação dentro das 48h
    # Aluno Pós confirma sua matrícula
    res_conf = client.post(f"/matriculas/{m_pos['id']}/confirmar")
    assert res_conf.status_code == 200
    assert res_conf.json()["estado"] == "confirmada"


def test_regra_2_expiracao_48h(client):
    # Turma com 1 vaga
    disc = client.post("/disciplinas", json={
        "codigo": "EXP01", "nome": "Topicos 2", "numero_creditos": 4, "carga_horaria": 60, "departamento": "TI"
    }).json()["id"]
    turma = client.post("/turmas", json={
        "disciplina_id": disc, "semestre": "2026.1", "professor": "Prof", "numero_vagas": 1, "horario": "SEG 08:00-10:00"
    }).json()["id"]

    # Aluno 1 ocupa vaga
    a1 = client.post("/alunos", json={
        "nome": "A1", "matricula": "M01", "e_mail": "m01@test.com", "categoria": "graduacao"
    }).json()["id"]
    m1 = client.post("/matriculas/solicitar", json={"aluno_id": a1, "turma_id": turma}).json()

    # Aluno 2 (Pos) e Aluno 3 (Grad) entram na fila
    a2_pos = client.post("/alunos", json={
        "nome": "A2 Pos", "matricula": "M02", "e_mail": "m02@test.com", "categoria": "pos"
    }).json()["id"]
    m2 = client.post("/matriculas/solicitar", json={"aluno_id": a2_pos, "turma_id": turma}).json()

    a3_grad = client.post("/alunos", json={
        "nome": "A3 Grad", "matricula": "M03", "e_mail": "m03@test.com", "categoria": "graduacao"
    }).json()["id"]
    m3 = client.post("/matriculas/solicitar", json={"aluno_id": a3_grad, "turma_id": turma}).json()

    # Vaga é liberada em t0
    t0 = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
    client.post(f"/matriculas/{m1['id']}/cancelar", json={"data_referencia": t0.isoformat()})

    # Aluno 2 (Pos) é o primeiro da fila. Tenta confirmar 50 horas depois (expirado!)
    t_expirado = t0 + timedelta(hours=50)
    res_exp = client.post(f"/matriculas/{m2['id']}/confirmar", json={"data_referencia": t_expirado.isoformat()})
    assert res_exp.status_code == 400
    assert "expirado" in res_exp.json()["detail"].lower()

    # Matrícula de m2 foi cancelada, e a vez passou para m3 (Graduação)
    m2_check = client.get(f"/matriculas/{m2['id']}").json()
    assert m2_check["estado"] == "cancelada"

    # Agora Aluno 3 confirma no t_expirado + 2 horas (dentro das novas 48h dele)
    res_conf3 = client.post(f"/matriculas/{m3['id']}/confirmar", json={"data_referencia": (t_expirado + timedelta(hours=2)).isoformat()})
    assert res_conf3.status_code == 200
    assert res_conf3.json()["estado"] == "confirmada"


def test_regra_3_tres_reprovacoes_bloqueia(client):
    disc = client.post("/disciplinas", json={
        "codigo": "REP01", "nome": "Cálculo Pesado", "numero_creditos": 4, "carga_horaria": 60, "departamento": "Mat"
    }).json()["id"]
    turma = client.post("/turmas", json={
        "disciplina_id": disc, "semestre": "2026.1", "professor": "Prof", "numero_vagas": 10, "horario": "SEG 08:00-10:00"
    }).json()["id"]
    aluno = client.post("/alunos", json={
        "nome": "Aluno Reprovado", "matricula": "REP001", "e_mail": "rep@test.com", "categoria": "graduacao"
    }).json()["id"]

    # 2 reprovações ainda pode matricular
    client.post("/historico", json={"aluno_id": aluno, "disciplina_id": disc, "semestre": "2024.1", "situacao": "reprovado"})
    client.post("/historico", json={"aluno_id": aluno, "disciplina_id": disc, "semestre": "2024.2", "situacao": "reprovado"})

    # Pode matricular com 2 reprovações
    m_ok = client.post("/matriculas/solicitar", json={"aluno_id": aluno, "turma_id": turma})
    assert m_ok.status_code == 201

    # Cancela para testar a 3ª reprovação
    client.post(f"/matriculas/{m_ok.json()['id']}/cancelar")

    # Registra a 3ª reprovação
    client.post("/historico", json={"aluno_id": aluno, "disciplina_id": disc, "semestre": "2025.1", "situacao": "reprovado"})

    # Tentativa com 3 reprovações -> 400 Bad Request
    m_bloq = client.post("/matriculas/solicitar", json={"aluno_id": aluno, "turma_id": turma})
    assert m_bloq.status_code == 400
    assert "3 reprovações" in m_bloq.json()["detail"].lower() or "máximo permitido" in m_bloq.json()["detail"].lower()


def test_regra_4_trancamento_e_cancelamento(client):
    # Graduação: máx 2 trancamentos, prazo 15 dias
    disc = client.post("/disciplinas", json={
        "codigo": "TR01", "nome": "Física Geral", "numero_creditos": 4, "carga_horaria": 60, "departamento": "Fis"
    }).json()["id"]
    turma = client.post("/turmas", json={
        "disciplina_id": disc, "semestre": "2026.1", "professor": "Prof", "numero_vagas": 10, "horario": "SEG 08:00-10:00"
    }).json()["id"]
    aluno_grad = client.post("/alunos", json={
        "nome": "Aluno Grad", "matricula": "TRG01", "e_mail": "trg01@test.com", "categoria": "graduacao"
    }).json()["id"]
    aluno_esp = client.post("/alunos", json={
        "nome": "Aluno Esp", "matricula": "TRE01", "e_mail": "tre01@test.com", "categoria": "especial"
    }).json()["id"]

    # 1. Categoria Especial NÃO pode trancar (limite 0)
    m_esp = client.post("/matriculas/solicitar", json={"aluno_id": aluno_esp, "turma_id": turma}).json()
    res_tranc_esp = client.post(f"/matriculas/{m_esp['id']}/trancar")
    assert res_tranc_esp.status_code == 400
    assert "especial" in res_tranc_esp.json()["detail"].lower()

    # 2. Graduação tranca dentro do prazo (10 dias)
    m_grad = client.post("/matriculas/solicitar", json={"aluno_id": aluno_grad, "turma_id": turma}).json()
    t_mat = datetime.fromisoformat(m_grad["data"].replace("Z", "+00:00"))

    t_10d = t_mat + timedelta(days=10)
    res_tranc1 = client.post(f"/matriculas/{m_grad['id']}/trancar", json={"data_referencia": t_10d.isoformat()})
    assert res_tranc1.status_code == 200

    # Histórico deve conter registro de trancado
    hist = client.get(f"/historico/aluno/{aluno_grad}").json()
    assert len(hist) == 1
    assert hist[0]["situacao"] == "trancado"

    # 3. Cancelamento FORA do prazo (Graduação prazo é 15 dias. Tentativa em 20 dias)
    # Registra nova matrícula para testar cancelamento fora do prazo
    m_grad2 = client.post("/matriculas/solicitar", json={"aluno_id": aluno_grad, "turma_id": turma}).json()
    t_mat2 = datetime.fromisoformat(m_grad2["data"].replace("Z", "+00:00"))
    t_20d = t_mat2 + timedelta(days=20)

    res_canc_fora = client.post(f"/matriculas/{m_grad2['id']}/cancelar", json={"data_referencia": t_20d.isoformat()})
    assert res_canc_fora.status_code == 200
    assert "reprovação por falta" in res_canc_fora.json()["mensagem"].lower()

    # Checar se no histórico consta reprovação por falta
    hist2 = client.get(f"/historico/aluno/{aluno_grad}").json()
    situacoes = [h["situacao"] for h in hist2]
    assert "reprovado_por_falta" in situacoes


def test_regra_5_turma_menos_de_5_alunos_cancelada(client):
    disc = client.post("/disciplinas", json={
        "codigo": "R501", "nome": "Eletromagnetismo", "numero_creditos": 4, "carga_horaria": 60, "departamento": "Fis"
    }).json()["id"]
    turma = client.post("/turmas", json={
        "disciplina_id": disc, "semestre": "2026.1", "professor": "Prof", "numero_vagas": 20, "horario": "SEG 08:00-10:00"
    }).json()["id"]

    # Matricular apenas 3 alunos (menos de 5)
    matriculas_ids = []
    for i in range(1, 4):
        aluno = client.post("/alunos", json={
            "nome": f"Aluno {i}", "matricula": f"M50{i}", "e_mail": f"m50{i}@test.com", "categoria": "graduacao"
        }).json()["id"]
        m = client.post("/matriculas/solicitar", json={"aluno_id": aluno, "turma_id": turma}).json()
        matriculas_ids.append(m["id"])

    # Encerrar período de matrícula
    res_fim = client.post(f"/turmas/{turma}/encerrar-periodo-matricula")
    assert res_fim.status_code == 200
    assert res_fim.json()["estado"] == "cancelada"

    # Turma cancelada
    turma_get = client.get(f"/turmas/{turma}").json()
    assert turma_get["estado"] == "cancelada"

    # Todas as matrículas canceladas
    for mid in matriculas_ids:
        m_check = client.get(f"/matriculas/{mid}").json()
        assert m_check["estado"] == "cancelada"


def test_regra_6_conflito_de_horarios(client):
    disc1 = client.post("/disciplinas", json={
        "codigo": "CONF1", "nome": "Redes 1", "numero_creditos": 4, "carga_horaria": 60, "departamento": "TI"
    }).json()["id"]
    disc2 = client.post("/disciplinas", json={
        "codigo": "CONF2", "nome": "Sistemas Operacionais", "numero_creditos": 4, "carga_horaria": 60, "departamento": "TI"
    }).json()["id"]

    # Turma 1: SEG 08:00-10:00
    t1 = client.post("/turmas", json={
        "disciplina_id": disc1, "semestre": "2026.1", "professor": "Prof A", "numero_vagas": 20, "horario": "SEG 08:00-10:00"
    }).json()["id"]

    # Turma 2: SEG 09:00-11:00 (Conflita com Turma 1)
    t2 = client.post("/turmas", json={
        "disciplina_id": disc2, "semestre": "2026.1", "professor": "Prof B", "numero_vagas": 20, "horario": "SEG 09:00-11:00"
    }).json()["id"]

    aluno = client.post("/alunos", json={
        "nome": "Aluno Conflito", "matricula": "CONF01", "e_mail": "conf01@test.com", "categoria": "graduacao"
    }).json()["id"]

    # Matrícula na primeira
    res_m1 = client.post("/matriculas/solicitar", json={"aluno_id": aluno, "turma_id": t1})
    assert res_m1.status_code == 201

    # Matrícula na segunda -> Choque de horário -> 400 Bad Request
    res_m2 = client.post("/matriculas/solicitar", json={"aluno_id": aluno, "turma_id": t2})
    assert res_m2.status_code == 400
    assert "conflito" in res_m2.json()["detail"].lower()


def test_regra_7_tres_trancamentos_no_semestre(client):
    # Aluno que acumular 3 trancamentos no semestre passa para situação 'trancado'
    # e todas as suas matrículas confirmadas são canceladas
    aluno = client.post("/alunos", json={
        "nome": "Aluno R7", "matricula": "R701", "e_mail": "r701@test.com", "categoria": "graduacao"
    }).json()["id"]

    # Criar 4 disciplinas e 4 turmas no mesmo semestre em horários sem conflito
    turmas = []
    dias = ["SEG", "TER", "QUA", "QUI"]
    for i in range(4):
        d = client.post("/disciplinas", json={
            "codigo": f"R7D{i}", "nome": f"Disciplina {i}", "numero_creditos": 4, "carga_horaria": 60, "departamento": "Geral"
        }).json()["id"]
        t = client.post("/turmas", json={
            "disciplina_id": d, "semestre": "2026.1", "professor": "Prof", "numero_vagas": 20, "horario": f"{dias[i]} 08:00-10:00"
        }).json()["id"]
        turmas.append(t)

    # Matricular nas 4
    matriculas = []
    for t in turmas:
        m = client.post("/matriculas/solicitar", json={"aluno_id": aluno, "turma_id": t}).json()
        assert m["estado"] == "confirmada"
        matriculas.append(m["id"])

    # Trancamento 1
    res1 = client.post(f"/matriculas/{matriculas[0]}/trancar")
    assert res1.status_code == 200
    aluno_check = client.get(f"/alunos/{aluno}").json()
    assert aluno_check["situacao"] == "ativo"

    # Trancamento 2
    res2 = client.post(f"/matriculas/{matriculas[1]}/trancar")
    assert res2.status_code == 200
    aluno_check = client.get(f"/alunos/{aluno}").json()
    assert aluno_check["situacao"] == "ativo"

    # Trancamento 3 -> Acumulou 3 trancamentos no semestre!
    res3 = client.post(f"/matriculas/{matriculas[2]}/trancar")
    assert res3.status_code == 200

    # 1. Aluno passa a situação 'trancado'
    aluno_check3 = client.get(f"/alunos/{aluno}").json()
    assert aluno_check3["situacao"] == "trancado"

    # 2. A 4ª matrícula (que estava confirmada) foi automaticamente cancelada!
    m4_check = client.get(f"/matriculas/{matriculas[3]}").json()
    assert m4_check["estado"] == "cancelada"
