"""Testes unitários e de integração para endpoints de Turmas."""

import pytest


def test_crud_turma(client):
    r_disc = client.post("/disciplinas", json={"codigo": "DCC001", "nome": "Algoritmos", "numero_creditos": 4, "carga_horaria": 60, "departamento": "DCC"})
    disc_id = r_disc.json()["id"]

    payload = {
        "disciplina_id": disc_id,
        "semestre": "2026.1",
        "professor": "Prof. Alan Turing",
        "numero_vagas": 40,
        "horario": "SEG 08:00-10:00, QUA 08:00-10:00",
        "estado": "aberta"
    }
    r = client.post("/turmas", json=payload)
    assert r.status_code == 201
    turma_id = r.json()["id"]
    assert r.json()["professor"] == "Prof. Alan Turing"
    assert r.json()["numero_vagas"] == 40
    assert r.json()["vagas_disponiveis"] == 40
    assert r.json()["vagas_ocupadas"] == 0

    # Get
    r_get = client.get(f"/turmas/{turma_id}")
    assert r_get.status_code == 200
    assert r_get.json()["id"] == turma_id

    # Update
    r_up = client.put(f"/turmas/{turma_id}", json={"numero_vagas": 45})
    assert r_up.status_code == 200
    assert r_up.json()["numero_vagas"] == 45

    # Delete
    r_del = client.delete(f"/turmas/{turma_id}")
    assert r_del.status_code == 204
