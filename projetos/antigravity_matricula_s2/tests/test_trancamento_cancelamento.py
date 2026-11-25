"""Testes unitários e de integração para Regra 4 (trancamento/cancelamento) e Regra 7 (limite semestral)."""

import pytest
from datetime import datetime, timezone, timedelta


def test_regra4_limite_trancamentos_por_categoria(client):
    # Especial: 0 trancamentos
    # Pos: 1 trancamento
    # Graduacao: 2 trancamentos

    d1 = client.post("/disciplinas", json={"codigo": "D1", "nome": "Disc 1", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    t1 = client.post("/turmas", json={"disciplina_id": d1, "semestre": "2026.1", "professor": "P1", "numero_vagas": 20, "horario": "SEG 08:00-10:00"}).json()["id"]

    # 1. Aluno Especial tentando trancar (limite 0)
    a_esp = client.post("/alunos", json={"nome": "Esp", "matricula": "E1", "email": "e@u.br", "categoria": "especial"}).json()["id"]
    m_esp = client.post("/matriculas/solicitar", json={"aluno_id": a_esp, "turma_id": t1}).json()["id"]

    r_tranc_esp = client.post(f"/matriculas/{m_esp}/trancar")
    assert r_tranc_esp.status_code == 400
    assert "limite de trancamentos" in r_tranc_esp.json()["detail"].lower()

    # 2. Aluno Pós (limite 1 trancamento)
    a_pos = client.post("/alunos", json={"nome": "Pos", "matricula": "P1", "email": "p@u.br", "categoria": "pos"}).json()["id"]
    m_pos1 = client.post("/matriculas/solicitar", json={"aluno_id": a_pos, "turma_id": t1}).json()["id"]

    # 1º trancamento: OK
    r_tranc_pos1 = client.post(f"/matriculas/{m_pos1}/trancar")
    assert r_tranc_pos1.status_code == 200
    assert r_tranc_pos1.json()["estado"] == "trancada"

    # Criamos outra turma da mesma disciplina em semestre posterior para tentar 2º trancamento
    t1_futura = client.post("/turmas", json={"disciplina_id": d1, "semestre": "2026.2", "professor": "P1", "numero_vagas": 20, "horario": "SEG 08:00-10:00"}).json()["id"]
    m_pos2 = client.post("/matriculas/solicitar", json={"aluno_id": a_pos, "turma_id": t1_futura}).json()["id"]

    # 2º trancamento na mesma disciplina para Pós: NEGADO!
    r_tranc_pos2 = client.post(f"/matriculas/{m_pos2}/trancar")
    assert r_tranc_pos2.status_code == 400
    assert "limite de trancamentos" in r_tranc_pos2.json()["detail"].lower()


def test_regra4_prazo_cancelamento_e_reprovacao_por_falta(client):
    # Graduação: prazo de cancelamento é 15 dias
    d1 = client.post("/disciplinas", json={"codigo": "MAT555", "nome": "Cálculo", "numero_creditos": 4, "carga_horaria": 60, "departamento": "MAT"}).json()["id"]
    t1 = client.post("/turmas", json={"disciplina_id": d1, "semestre": "2026.1", "professor": "P", "numero_vagas": 20, "horario": "SEG 08:00-10:00"}).json()["id"]

    a_grad = client.post("/alunos", json={"nome": "Grad", "matricula": "G1", "email": "g@u.br", "categoria": "graduacao"}).json()["id"]

    # Matrícula feita no dia 01/01
    dt_matricula = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    m = client.post("/matriculas/solicitar", json={"aluno_id": a_grad, "turma_id": t1, "data": dt_matricula.isoformat()}).json()
    m_id = m["id"]

    # Tentativa de trancamento no dia 25/01 (24 dias depois -> prazo é 15 dias -> FORA DO PRAZO)
    dt_fora = datetime(2026, 1, 25, 10, 0, 0, tzinfo=timezone.utc)
    r_tranc_fora = client.post(f"/matriculas/{m_id}/trancar?data_trancamento={dt_fora.isoformat()}")
    assert r_tranc_fora.status_code == 200
    # Fora do prazo: cancela a matrícula e registra reprovação por falta
    assert r_tranc_fora.json()["estado"] == "cancelada"

    # Verifica no Histórico se registrou reprovação por falta!
    r_hist = client.get(f"/historico/aluno/{a_grad}")
    assert r_hist.status_code == 200
    hist = r_hist.json()
    assert len(hist) == 1
    assert hist[0]["situacao"] == "reprovado_por_falta"
    assert hist[0]["disciplina_id"] == d1


def test_regra7_tres_trancamentos_trancam_aluno(client):
    # Aluno que acumular três trancamentos no semestre passa à situação 'trancado',
    # e todas as suas matrículas confirmadas são canceladas.

    a_grad = client.post("/alunos", json={"nome": "Ana Multi", "matricula": "AN1", "email": "ana@u.br", "categoria": "graduacao"}).json()["id"]

    # 4 disciplinas distintas
    d1 = client.post("/disciplinas", json={"codigo": "D1", "nome": "Disc 1", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    d2 = client.post("/disciplinas", json={"codigo": "D2", "nome": "Disc 2", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    d3 = client.post("/disciplinas", json={"codigo": "D3", "nome": "Disc 3", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    d4 = client.post("/disciplinas", json={"codigo": "D4", "nome": "Disc 4", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]

    t1 = client.post("/turmas", json={"disciplina_id": d1, "semestre": "2026.1", "professor": "P1", "numero_vagas": 20, "horario": "SEG 08:00-10:00"}).json()["id"]
    t2 = client.post("/turmas", json={"disciplina_id": d2, "semestre": "2026.1", "professor": "P2", "numero_vagas": 20, "horario": "TER 08:00-10:00"}).json()["id"]
    t3 = client.post("/turmas", json={"disciplina_id": d3, "semestre": "2026.1", "professor": "P3", "numero_vagas": 20, "horario": "QUA 08:00-10:00"}).json()["id"]
    t4 = client.post("/turmas", json={"disciplina_id": d4, "semestre": "2026.1", "professor": "P4", "numero_vagas": 20, "horario": "QUI 08:00-10:00"}).json()["id"]

    # Matricula nas 4 turmas (dentro do limite de 28 créditos)
    m1 = client.post("/matriculas/solicitar", json={"aluno_id": a_grad, "turma_id": t1}).json()["id"]
    m2 = client.post("/matriculas/solicitar", json={"aluno_id": a_grad, "turma_id": t2}).json()["id"]
    m3 = client.post("/matriculas/solicitar", json={"aluno_id": a_grad, "turma_id": t3}).json()["id"]
    m4 = client.post("/matriculas/solicitar", json={"aluno_id": a_grad, "turma_id": t4}).json()["id"]

    # 1º trancamento (t1) -> aluno continua ativo
    client.post(f"/matriculas/{m1}/trancar")
    assert client.get(f"/alunos/{a_grad}").json()["situacao"] == "ativo"

    # 2º trancamento (t2) -> aluno continua ativo
    client.post(f"/matriculas/{m2}/trancar")
    assert client.get(f"/alunos/{a_grad}").json()["situacao"] == "ativo"

    # 3º trancamento (t3) -> atinge 3 trancamentos no semestre!
    client.post(f"/matriculas/{m3}/trancar")

    # Aluno deve agora estar TRANCADO!
    aluno_atualizado = client.get(f"/alunos/{a_grad}").json()
    assert aluno_atualizado["situacao"] == "trancado"

    # E sua 4ª matrícula (m4), que estava confirmada, agora deve estar CANCELADA!
    m4_atualizada = client.get(f"/matriculas/{m4}").json()
    assert m4_atualizada["estado"] == "cancelada"
