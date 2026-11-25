"""Testes de validação de dados de entrada, erros HTTP e endpoints complementares."""

import pytest
from datetime import datetime, timezone, timedelta


def test_lista_de_espera_empate_data_solicitacao(client):
    r_disc = client.post("/disciplinas", json={"codigo": "EMP101", "nome": "Empate Test", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"})
    disc_id = r_disc.json()["id"]

    r_turma = client.post("/turmas", json={"disciplina_id": disc_id, "semestre": "2026.1", "professor": "Prof X", "numero_vagas": 1, "horario": "SEG 10:00-12:00"})
    turma_id = r_turma.json()["id"]

    # Cria 3 alunos da mesma categoria (graduacao)
    a1 = client.post("/alunos", json={"nome": "Titular", "matricula": "T1", "email": "t1@u.br", "categoria": "graduacao"}).json()["id"]
    a2 = client.post("/alunos", json={"nome": "Primeiro da Fila", "matricula": "F1", "email": "f1@u.br", "categoria": "graduacao"}).json()["id"]
    a3 = client.post("/alunos", json={"nome": "Segundo da Fila", "matricula": "F2", "email": "f2@u.br", "categoria": "graduacao"}).json()["id"]

    t0 = datetime(2026, 2, 1, 8, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 2, 1, 9, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 2, 1, 10, 0, 0, tzinfo=timezone.utc)

    # Titular pega a vaga
    client.post("/matriculas/solicitar", json={"aluno_id": a1, "turma_id": turma_id, "data": t0.isoformat()})
    # Primeiro da fila às 09:00
    client.post("/matriculas/solicitar", json={"aluno_id": a2, "turma_id": turma_id, "data": t1.isoformat()})
    # Segundo da fila às 10:00
    client.post("/matriculas/solicitar", json={"aluno_id": a3, "turma_id": turma_id, "data": t2.isoformat()})

    # Consulta fila de espera
    r_fila = client.get(f"/lista-de-espera/{turma_id}")
    assert r_fila.status_code == 200
    fila = r_fila.json()
    assert len(fila) == 2
    assert fila[0]["aluno_id"] == a2
    assert fila[0]["posicao"] == 1
    assert fila[1]["aluno_id"] == a3
    assert fila[1]["posicao"] == 2


def test_matriculas_listar_por_aluno(client):
    d1 = client.post("/disciplinas", json={"codigo": "DISC1", "nome": "Disciplina 1", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"}).json()["id"]
    t1 = client.post("/turmas", json={"disciplina_id": d1, "semestre": "2026.1", "professor": "Prof 1", "numero_vagas": 20, "horario": "SEG 08:00-10:00"}).json()["id"]

    a1 = client.post("/alunos", json={"nome": "Aluno Teste", "matricula": "ALU1", "email": "alu1@u.br", "categoria": "graduacao"}).json()["id"]

    # Matricula o aluno
    r_sol = client.post("/matriculas/solicitar", json={"aluno_id": a1, "turma_id": t1})
    assert r_sol.status_code == 201

    # Consulta por aluno (/matriculas/aluno/{id})
    r_lista = client.get(f"/matriculas/aluno/{a1}")
    assert r_lista.status_code == 200
    lista = r_lista.json()
    assert len(lista) == 1
    assert lista[0]["aluno_id"] == a1
    assert lista[0]["disciplina_codigo"] == "DISC1"

    # Consulta por filtro de query (/matriculas?aluno_id={id})
    r_query = client.get(f"/matriculas?aluno_id={a1}")
    assert r_query.status_code == 200
    assert len(r_query.json()) == 1


def test_historico_crud_e_consulta_por_aluno(client):
    a1 = client.post("/alunos", json={"nome": "Estudante", "matricula": "EST1", "email": "est@u.br", "categoria": "graduacao"}).json()["id"]
    d1 = client.post("/disciplinas", json={"codigo": "MAT01", "nome": "Cálculo", "numero_creditos": 4, "carga_horaria": 60, "departamento": "MAT"}).json()["id"]

    # Inserir no histórico
    r_add = client.post("/historico", json={
        "aluno_id": a1,
        "disciplina_id": d1,
        "semestre": "2025.1",
        "nota": 9.2,
        "situacao": "aprovado"
    })
    assert r_add.status_code == 201
    hist_id = r_add.json()["id"]
    assert r_add.json()["nota"] == 9.2
    assert r_add.json()["situacao"] == "aprovado"

    # Consultar por aluno
    r_get = client.get(f"/historico/aluno/{a1}")
    assert r_get.status_code == 200
    assert len(r_get.json()) == 1
    assert r_get.json()[0]["disciplina_codigo"] == "MAT01"

    # Atualizar registro
    r_up = client.put(f"/historico/{hist_id}", json={"nota": 9.5})
    assert r_up.status_code == 200
    assert r_up.json()["nota"] == 9.5

    # Deletar registro
    r_del = client.delete(f"/historico/{hist_id}")
    assert r_del.status_code == 204


def test_validacoes_de_entrada_e_erros_http(client):
    # E-mail inválido -> 422
    r_inv_email = client.post("/alunos", json={"nome": "X", "matricula": "M", "email": "email-invalido", "categoria": "graduacao"})
    assert r_inv_email.status_code == 422

    # Categoria inválida -> 422
    r_inv_cat = client.post("/alunos", json={"nome": "X", "matricula": "M", "email": "x@u.br", "categoria": "categoria_fantasma"})
    assert r_inv_cat.status_code == 422

    # Créditos <= 0 -> 422
    r_inv_cred = client.post("/disciplinas", json={"codigo": "X", "nome": "X", "numero_creditos": 0, "carga_horaria": 60, "departamento": "D"})
    assert r_inv_cred.status_code == 422

    # Vagas < 0 -> 422
    r_inv_vagas = client.post("/turmas", json={"disciplina_id": 1, "semestre": "2026.1", "professor": "P", "numero_vagas": -5, "horario": "SEG 08:00-10:00"})
    assert r_inv_vagas.status_code == 422

    # Aluno inexistente -> 404
    r_404_aluno = client.get("/alunos/99999")
    assert r_404_aluno.status_code == 404

    # Disciplina inexistente -> 404
    r_404_disc = client.get("/disciplinas/99999")
    assert r_404_disc.status_code == 404

    # Turma inexistente -> 404
    r_404_turma = client.get("/turmas/99999")
    assert r_404_turma.status_code == 404

    # Matrícula inexistente -> 404
    r_404_mat = client.get("/matriculas/99999")
    assert r_404_mat.status_code == 404
