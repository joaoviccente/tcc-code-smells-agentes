from datetime import datetime, timezone, timedelta
import pytest

def test_empate_na_fila_de_espera_mesma_categoria(client):
    """Verifica desempate por data da solicitação quando a categoria é igual."""
    disc = client.post("/disciplinas", json={
        "codigo": "EMP01", "nome": "Desempate", "numero_creditos": 4, "carga_horaria": 60, "departamento": "TI"
    }).json()["id"]
    turma = client.post("/turmas", json={
        "disciplina_id": disc, "semestre": "2026.1", "professor": "Prof", "numero_vagas": 1, "horario": "SEG 08:00-10:00"
    }).json()["id"]

    # Aluno que ocupa a vaga
    aluno_vaga = client.post("/alunos", json={
        "nome": "Ocupa Vaga", "matricula": "OC01", "e_mail": "oc01@test.com", "categoria": "graduacao"
    }).json()["id"]
    client.post("/matriculas/solicitar", json={"aluno_id": aluno_vaga, "turma_id": turma})

    # Aluno G1 solicita às 10:00
    aluno_g1 = client.post("/alunos", json={
        "nome": "Grad 1 Mais Antigo", "matricula": "G1", "e_mail": "g1@test.com", "categoria": "graduacao"
    }).json()["id"]
    client.post("/matriculas/solicitar", json={"aluno_id": aluno_g1, "turma_id": turma})

    # Aluno G2 solicita depois
    aluno_g2 = client.post("/alunos", json={
        "nome": "Grad 2 Mais Recente", "matricula": "G2", "e_mail": "g2@test.com", "categoria": "graduacao"
    }).json()["id"]
    client.post("/matriculas/solicitar", json={"aluno_id": aluno_g2, "turma_id": turma})

    fila = client.get(f"/turmas/{turma}/fila").json()["fila"]
    assert len(fila) == 2
    assert fila[0]["aluno_id"] == aluno_g1
    assert fila[1]["aluno_id"] == aluno_g2


def test_pos_limite_trancamento_e_prazos(client):
    """Testa regras específicas da categoria Pós (máx 1 trancamento, 30 dias de prazo)."""
    disc = client.post("/disciplinas", json={
        "codigo": "POS_R", "nome": "Tópicos de Pós", "numero_creditos": 4, "carga_horaria": 60, "departamento": "TI"
    }).json()["id"]
    turma = client.post("/turmas", json={
        "disciplina_id": disc, "semestre": "2026.1", "professor": "Prof", "numero_vagas": 10, "horario": "SEG 08:00-10:00"
    }).json()["id"]
    aluno_pos = client.post("/alunos", json={
        "nome": "Aluno Pos", "matricula": "POS_EX", "e_mail": "pos_ex@test.com", "categoria": "pos"
    }).json()["id"]

    # 1. Matricular e trancar 1 vez no 20º dia (dentro dos 30 dias) -> Sucesso
    m1 = client.post("/matriculas/solicitar", json={"aluno_id": aluno_pos, "turma_id": turma}).json()
    t_m1 = datetime.fromisoformat(m1["data"].replace("Z", "+00:00"))
    t_20d = t_m1 + timedelta(days=20)
    res_tranc1 = client.post(f"/matriculas/{m1['id']}/trancar", json={"data_referencia": t_20d.isoformat()})
    assert res_tranc1.status_code == 200

    # 2. Tentar trancar pela 2ª vez na mesma disciplina -> Falha (limite de 1 para Pós)
    m2 = client.post("/matriculas/solicitar", json={"aluno_id": aluno_pos, "turma_id": turma}).json()
    t_m2 = datetime.fromisoformat(m2["data"].replace("Z", "+00:00"))
    t_10d = t_m2 + timedelta(days=10)
    res_tranc2 = client.post(f"/matriculas/{m2['id']}/trancar", json={"data_referencia": t_10d.isoformat()})
    assert res_tranc2.status_code == 400
    assert "limite de trancamentos" in res_tranc2.json()["detail"].lower()

    # 3. Cancelamento após 31 dias (prazo é 30 dias) -> Registra reprovação por falta
    t_31d = t_m2 + timedelta(days=31)
    res_canc = client.post(f"/matriculas/{m2['id']}/cancelar", json={"data_referencia": t_31d.isoformat()})
    assert res_canc.status_code == 200
    assert "reprovação por falta" in res_canc.json()["mensagem"].lower()


def test_especial_prazos_cancelamento(client):
    """Testa prazos específicos da categoria Especial (prazo de cancelamento 7 dias)."""
    disc = client.post("/disciplinas", json={
        "codigo": "ESP_R", "nome": "Especial Disc", "numero_creditos": 4, "carga_horaria": 60, "departamento": "TI"
    }).json()["id"]
    turma = client.post("/turmas", json={
        "disciplina_id": disc, "semestre": "2026.1", "professor": "Prof", "numero_vagas": 10, "horario": "SEG 08:00-10:00"
    }).json()["id"]
    aluno_esp = client.post("/alunos", json={
        "nome": "Aluno Especial", "matricula": "ESP_PZ", "e_mail": "esp_pz@test.com", "categoria": "especial"
    }).json()["id"]

    # 1. Cancelamento dentro de 5 dias (<= 7) -> Limpo sem reprovação
    m1 = client.post("/matriculas/solicitar", json={"aluno_id": aluno_esp, "turma_id": turma}).json()
    t_m1 = datetime.fromisoformat(m1["data"].replace("Z", "+00:00"))
    res_canc_ok = client.post(f"/matriculas/{m1['id']}/cancelar", json={"data_referencia": (t_m1 + timedelta(days=5)).isoformat()})
    assert res_canc_ok.status_code == 200
    hist = client.get(f"/historico/aluno/{aluno_esp}").json()
    assert len(hist) == 0

    # 2. Cancelamento no 8º dia (> 7) -> Reprovação por falta
    m2 = client.post("/matriculas/solicitar", json={"aluno_id": aluno_esp, "turma_id": turma}).json()
    t_m2 = datetime.fromisoformat(m2["data"].replace("Z", "+00:00"))
    res_canc_falta = client.post(f"/matriculas/{m2['id']}/cancelar", json={"data_referencia": (t_m2 + timedelta(days=8)).isoformat()})
    assert res_canc_falta.status_code == 200
    assert "reprovação por falta" in res_canc_falta.json()["mensagem"].lower()
    hist2 = client.get(f"/historico/aluno/{aluno_esp}").json()
    assert len(hist2) == 1
    assert hist2[0]["situacao"] == "reprovado_por_falta"


def test_aluno_jubilado_bloqueado(client):
    """Aluno jubilado não pode solicitar matrícula."""
    disc = client.post("/disciplinas", json={
        "codigo": "JUB01", "nome": "Disciplina", "numero_creditos": 4, "carga_horaria": 60, "departamento": "TI"
    }).json()["id"]
    turma = client.post("/turmas", json={
        "disciplina_id": disc, "semestre": "2026.1", "professor": "Prof", "numero_vagas": 10, "horario": "SEG 08:00-10:00"
    }).json()["id"]
    aluno_jub = client.post("/alunos", json={
        "nome": "Aluno Jubilado", "matricula": "JUB01", "e_mail": "jub@test.com", "categoria": "graduacao", "situacao": "jubilado"
    }).json()["id"]

    res = client.post("/matriculas/solicitar", json={"aluno_id": aluno_jub, "turma_id": turma})
    assert res.status_code == 400
    assert "jubilado" in res.json()["detail"].lower()


def test_turma_com_5_alunos_mantida_ao_fim_do_periodo(client):
    """Turma com exatamente 5 alunos é mantida ao fim do período."""
    disc = client.post("/disciplinas", json={
        "codigo": "OK501", "nome": "Disciplina 5 Alunos", "numero_creditos": 4, "carga_horaria": 60, "departamento": "TI"
    }).json()["id"]
    turma = client.post("/turmas", json={
        "disciplina_id": disc, "semestre": "2026.1", "professor": "Prof", "numero_vagas": 10, "horario": "SEG 08:00-10:00"
    }).json()["id"]

    for i in range(5):
        aluno = client.post("/alunos", json={
            "nome": f"Aluno {i}", "matricula": f"OK50{i}", "e_mail": f"ok50{i}@test.com", "categoria": "graduacao"
        }).json()["id"]
        client.post("/matriculas/solicitar", json={"aluno_id": aluno, "turma_id": turma})

    res_fim = client.post(f"/turmas/{turma}/encerrar-periodo-matricula")
    assert res_fim.status_code == 200
    assert res_fim.json()["estado"] == "encerrada"
    assert res_fim.json()["matriculas_confirmadas"] == 5
