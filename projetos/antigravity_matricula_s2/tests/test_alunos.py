"""Testes unitários e de integração para endpoints de Alunos."""

import pytest


def test_criar_aluno_sucesso(client):
    payload = {
        "nome": "João Silva",
        "matricula": "2026001",
        "email": "joao.silva@universidade.edu.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }
    response = client.post("/alunos", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["nome"] == "João Silva"
    assert data["matricula"] == "2026001"
    assert data["categoria"] == "graduacao"
    assert data["situacao"] == "ativo"
    assert data["max_creditos"] == 28
    assert data["limite_trancamentos"] == 2
    assert data["prazo_cancelamento_dias"] == 15
    assert data["prioridade_espera"] == "media"


def test_criar_aluno_pos_e_especial(client):
    # Pós
    p_pos = {
        "nome": "Maria Doutoranda",
        "matricula": "2026POS01",
        "email": "maria@universidade.edu.br",
        "categoria": "pos",
    }
    r_pos = client.post("/alunos", json=p_pos)
    assert r_pos.status_code == 201
    assert r_pos.json()["max_creditos"] == 16
    assert r_pos.json()["limite_trancamentos"] == 1
    assert r_pos.json()["prazo_cancelamento_dias"] == 30
    assert r_pos.json()["prioridade_espera"] == "alta"

    # Especial
    p_esp = {
        "nome": "Carlos Especial",
        "matricula": "2026ESP01",
        "email": "carlos@universidade.edu.br",
        "categoria": "especial",
    }
    r_esp = client.post("/alunos", json=p_esp)
    assert r_esp.status_code == 201
    assert r_esp.json()["max_creditos"] == 8
    assert r_esp.json()["limite_trancamentos"] == 0
    assert r_esp.json()["prazo_cancelamento_dias"] == 7
    assert r_esp.json()["prioridade_espera"] == "baixa"


def test_aluno_matricula_ou_email_duplicado(client):
    p1 = {
        "nome": "Aluno 1",
        "matricula": "MAT123",
        "email": "aluno1@universidade.edu.br",
        "categoria": "graduacao"
    }
    r1 = client.post("/alunos", json=p1)
    assert r1.status_code == 201

    # Matrícula duplicada
    p2 = {
        "nome": "Aluno 2",
        "matricula": "MAT123",
        "email": "outro@universidade.edu.br",
        "categoria": "graduacao"
    }
    r2 = client.post("/alunos", json=p2)
    assert r2.status_code == 409

    # Email duplicado
    p3 = {
        "nome": "Aluno 3",
        "matricula": "MAT456",
        "email": "aluno1@universidade.edu.br",
        "categoria": "graduacao"
    }
    r3 = client.post("/alunos", json=p3)
    assert r3.status_code == 409


def test_listar_e_filtrar_alunos(client):
    client.post("/alunos", json={"nome": "Ana Lima", "matricula": "A1", "email": "ana@u.br", "categoria": "graduacao", "situacao": "ativo"})
    client.post("/alunos", json={"nome": "Bruno Souza", "matricula": "B2", "email": "bruno@u.br", "categoria": "pos", "situacao": "trancado"})
    client.post("/alunos", json={"nome": "Clara Mendes", "matricula": "C3", "email": "clara@u.br", "categoria": "especial", "situacao": "jubilado"})

    r_all = client.get("/alunos")
    assert r_all.status_code == 200
    assert len(r_all.json()) == 3

    r_pos = client.get("/alunos?categoria=pos")
    assert len(r_pos.json()) == 1
    assert r_pos.json()[0]["nome"] == "Bruno Souza"

    r_jub = client.get("/alunos?situacao=jubilado")
    assert len(r_jub.json()) == 1
    assert r_jub.json()[0]["nome"] == "Clara Mendes"

    r_termo = client.get("/alunos?termo=Bruno")
    assert len(r_termo.json()) == 1
    assert r_termo.json()[0]["matricula"] == "B2"


def test_crud_completo_aluno(client):
    r_create = client.post("/alunos", json={"nome": "Teste", "matricula": "T01", "email": "t01@u.br", "categoria": "graduacao"})
    a_id = r_create.json()["id"]

    r_get = client.get(f"/alunos/{a_id}")
    assert r_get.status_code == 200
    assert r_get.json()["matricula"] == "T01"

    r_put = client.put(f"/alunos/{a_id}", json={"nome": "Teste Atualizado", "situacao": "trancado"})
    assert r_put.status_code == 200
    assert r_put.json()["nome"] == "Teste Atualizado"
    assert r_put.json()["situacao"] == "trancado"

    r_del = client.delete(f"/alunos/{a_id}")
    assert r_del.status_code == 204

    r_get_del = client.get(f"/alunos/{a_id}")
    assert r_get_del.status_code == 404
