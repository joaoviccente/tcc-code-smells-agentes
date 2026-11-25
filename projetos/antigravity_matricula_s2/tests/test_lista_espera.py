"""Testes unitários e de integração para Regra 2: Lista de Espera, ordenação por categoria e prazo de 48h."""

import pytest
from datetime import datetime, timezone, timedelta


def test_regra2_lista_de_espera_e_ordenacao_por_categoria(client):
    r_disc = client.post("/disciplinas", json={"codigo": "DCC500", "nome": "IA", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"})
    disc_id = r_disc.json()["id"]

    # Cria turma com apenas 1 vaga
    r_turma = client.post("/turmas", json={"disciplina_id": disc_id, "semestre": "2026.1", "professor": "Turing", "numero_vagas": 1, "horario": "SEX 14:00-16:00"})
    turma_id = r_turma.json()["id"]

    # Cria alunos:
    # 1. Aluno 1 (Graduação) -> vai pegar a única vaga
    # 2. Aluno 2 (Especial) -> solicita às 10:00 (prioridade baixa)
    # 3. Aluno 3 (Graduação) -> solicita às 11:00 (prioridade média)
    # 4. Aluno 4 (Pós) -> solicita às 12:00 (prioridade alta)
    # 5. Aluno 5 (Graduação) -> solicita às 13:00 (prioridade média, empate com Aluno 3)
    a1 = client.post("/alunos", json={"nome": "A1 Grad", "matricula": "G1", "email": "g1@u.br", "categoria": "graduacao"}).json()["id"]
    a2 = client.post("/alunos", json={"nome": "A2 Esp", "matricula": "E1", "email": "e1@u.br", "categoria": "especial"}).json()["id"]
    a3 = client.post("/alunos", json={"nome": "A3 Grad", "matricula": "G2", "email": "g2@u.br", "categoria": "graduacao"}).json()["id"]
    a4 = client.post("/alunos", json={"nome": "A4 Pos", "matricula": "P1", "email": "p1@u.br", "categoria": "pos"}).json()["id"]
    a5 = client.post("/alunos", json={"nome": "A5 Grad", "matricula": "G3", "email": "g3@u.br", "categoria": "graduacao"}).json()["id"]

    t0 = datetime(2026, 1, 10, 9, 0, 0, tzinfo=timezone.utc)
    t_10 = datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc)
    t_11 = datetime(2026, 1, 10, 11, 0, 0, tzinfo=timezone.utc)
    t_12 = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
    t_13 = datetime(2026, 1, 10, 13, 0, 0, tzinfo=timezone.utc)

    # A1 pega a vaga
    m1 = client.post("/matriculas/solicitar", json={"aluno_id": a1, "turma_id": turma_id, "data": t0.isoformat()})
    assert m1.status_code == 201
    assert m1.json()["estado"] == "confirmada"

    # Turma agora está lotada
    r_t_check = client.get(f"/turmas/{turma_id}")
    assert r_t_check.json()["estado"] == "lotada"

    # A2 (Especial) entra na fila às 10:00
    m2 = client.post("/matriculas/solicitar", json={"aluno_id": a2, "turma_id": turma_id, "data": t_10.isoformat()})
    assert m2.status_code == 201
    assert m2.json()["estado"] == "lista_de_espera"

    # A3 (Graduação) entra na fila às 11:00
    m3 = client.post("/matriculas/solicitar", json={"aluno_id": a3, "turma_id": turma_id, "data": t_11.isoformat()})
    assert m3.status_code == 201
    assert m3.json()["estado"] == "lista_de_espera"

    # A4 (Pós) entra na fila às 12:00
    m4 = client.post("/matriculas/solicitar", json={"aluno_id": a4, "turma_id": turma_id, "data": t_12.isoformat()})
    assert m4.status_code == 201
    assert m4.json()["estado"] == "lista_de_espera"

    # A5 (Graduação) entra na fila às 13:00
    m5 = client.post("/matriculas/solicitar", json={"aluno_id": a5, "turma_id": turma_id, "data": t_13.isoformat()})
    assert m5.status_code == 201
    assert m5.json()["estado"] == "lista_de_espera"

    # Consulta fila de espera ordenada
    # Ordem esperada:
    # 1º: A4 (Pós - prioridade alta)
    # 2º: A3 (Graduação - prioridade média, solicitou às 11:00)
    # 3º: A5 (Graduação - prioridade média, solicitou às 13:00)
    # 4º: A2 (Especial - prioridade baixa, solicitou às 10:00)
    r_fila = client.get(f"/turmas/{turma_id}/lista-de-espera")
    assert r_fila.status_code == 200
    fila = r_fila.json()
    assert len(fila) == 4

    assert fila[0]["aluno_id"] == a4
    assert fila[0]["aluno_categoria"] == "pos"
    assert fila[0]["prioridade"] == "alta"

    assert fila[1]["aluno_id"] == a3
    assert fila[1]["aluno_categoria"] == "graduacao"
    assert fila[1]["prioridade"] == "media"

    assert fila[2]["aluno_id"] == a5
    assert fila[2]["aluno_categoria"] == "graduacao"
    assert fila[2]["prioridade"] == "media"

    assert fila[3]["aluno_id"] == a2
    assert fila[3]["aluno_categoria"] == "especial"
    assert fila[3]["prioridade"] == "baixa"


def test_regra2_liberacao_de_vaga_e_confirmacao_48h(client):
    r_disc = client.post("/disciplinas", json={"codigo": "MAT999", "nome": "Álgebra", "numero_creditos": 4, "carga_horaria": 60, "departamento": "MAT"})
    disc_id = r_disc.json()["id"]

    r_turma = client.post("/turmas", json={"disciplina_id": disc_id, "semestre": "2026.1", "professor": "Gauss", "numero_vagas": 1, "horario": "QUI 10:00-12:00"})
    turma_id = r_turma.json()["id"]

    a1 = client.post("/alunos", json={"nome": "Primeiro", "matricula": "M1", "email": "m1@u.br", "categoria": "graduacao"}).json()["id"]
    a2 = client.post("/alunos", json={"nome": "Segundo", "matricula": "M2", "email": "m2@u.br", "categoria": "pos"}).json()["id"]

    # A1 se matricula e pega a vaga
    m1 = client.post("/matriculas/solicitar", json={"aluno_id": a1, "turma_id": turma_id}).json()
    assert m1["estado"] == "confirmada"

    # A2 solicita e vai para lista de espera
    m2 = client.post("/matriculas/solicitar", json={"aluno_id": a2, "turma_id": turma_id}).json()
    assert m2["estado"] == "lista_de_espera"

    # A1 cancela a matrícula -> Vaga é liberada
    r_canc = client.post(f"/matriculas/{m1['id']}/cancelar")
    assert r_canc.status_code == 200

    # A2 agora deve ter sido promovido para 'solicitada' com prazo de confirmação de 48h
    r_m2_check = client.get(f"/matriculas/{m2['id']}")
    assert r_m2_check.status_code == 200
    m2_atualizada = r_m2_check.json()
    assert m2_atualizada["estado"] == "solicitada"
    assert m2_atualizada["data_limite_confirmacao"] is not None

    # A2 confirma a matrícula dentro do prazo
    r_conf = client.post(f"/matriculas/{m2['id']}/confirmar")
    assert r_conf.status_code == 200
    assert r_conf.json()["estado"] == "confirmada"


def test_regra2_prazo_48h_expirado_passa_ao_proximo(client, db_session):
    from app.models.matricula import Matricula

    r_disc = client.post("/disciplinas", json={"codigo": "FIS999", "nome": "Física Moderna", "numero_creditos": 4, "carga_horaria": 60, "departamento": "FIS"})
    disc_id = r_disc.json()["id"]

    r_turma = client.post("/turmas", json={"disciplina_id": disc_id, "semestre": "2026.1", "professor": "Einstein", "numero_vagas": 1, "horario": "QUA 14:00-16:00"})
    turma_id = r_turma.json()["id"]

    a1 = client.post("/alunos", json={"nome": "Titular", "matricula": "T1", "email": "t1@u.br", "categoria": "graduacao"}).json()["id"]
    a2 = client.post("/alunos", json={"nome": "Espera 1", "matricula": "E1", "email": "e1@u.br", "categoria": "pos"}).json()["id"]
    a3 = client.post("/alunos", json={"nome": "Espera 2", "matricula": "E2", "email": "e2@u.br", "categoria": "graduacao"}).json()["id"]

    m1_id = client.post("/matriculas/solicitar", json={"aluno_id": a1, "turma_id": turma_id}).json()["id"]
    m2_id = client.post("/matriculas/solicitar", json={"aluno_id": a2, "turma_id": turma_id}).json()["id"]
    m3_id = client.post("/matriculas/solicitar", json={"aluno_id": a3, "turma_id": turma_id}).json()["id"]

    # Titular cancela
    client.post(f"/matriculas/{m1_id}/cancelar")

    # Espera 1 (a2) é promovido para 'solicitada' com prazo
    m2 = client.get(f"/matriculas/{m2_id}").json()
    assert m2["estado"] == "solicitada"

    # Simulamos que o prazo de 48h expirou (setamos data_limite_confirmacao no passado)
    mat2_obj = db_session.query(Matricula).filter(Matricula.id == m2_id).first()
    mat2_obj.data_limite_confirmacao = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    # Tentativa de confirmação de m2 deve falhar por expiração de prazo
    r_tentativa = client.post(f"/matriculas/{m2_id}/confirmar")
    assert r_tentativa.status_code == 400
    assert "expirado" in r_tentativa.json()["detail"].lower()

    # m2 deve estar cancelada
    m2_after = client.get(f"/matriculas/{m2_id}").json()
    assert m2_after["estado"] == "cancelada"

    # E a vaga passou para o próximo (a3 / m3)
    m3_after = client.get(f"/matriculas/{m3_id}").json()
    assert m3_after["estado"] == "solicitada"
    assert m3_after["data_limite_confirmacao"] is not None
