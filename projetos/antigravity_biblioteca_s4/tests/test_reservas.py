from datetime import datetime, timedelta
from fastapi import status


def test_reservas_validacoes_e_cancelamento(client):
    hoje = datetime.now()

    u1 = client.post(
        "/usuarios",
        json={"nome": "User 1", "email": "u1@test.com", "matricula": "U01", "categoria": "aluno"},
    ).json()

    u2 = client.post(
        "/usuarios",
        json={"nome": "User 2", "email": "u2@test.com", "matricula": "U02", "categoria": "aluno"},
    ).json()

    u3 = client.post(
        "/usuarios",
        json={"nome": "User 3", "email": "u3@test.com", "matricula": "U03", "categoria": "aluno"},
    ).json()

    # Livro sem exemplares
    livro_vazio = client.post(
        "/livros",
        json={"titulo": "Livro Vazio", "autor": "Ninguém", "isbn": "0000", "ano": 2020, "area_conhecimento": "Geral"},
    ).json()

    # Tentar reservar livro sem exemplares -> 400
    resp_sem_ex = client.post("/reservas", json={"usuario_id": u1["id"], "livro_id": livro_vazio["id"]})
    assert resp_sem_ex.status_code == status.HTTP_400_BAD_REQUEST

    # Livro com exemplares
    livro = client.post(
        "/livros",
        json={"titulo": "Livro com Exemplares", "autor": "Autor", "isbn": "1111", "ano": 2021, "area_conhecimento": "Geral"},
    ).json()

    ex1 = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "EX-01"}).json()
    ex2 = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "EX-02"}).json()

    # Cria reservas: u1 entra em pos 1, u2 entra em pos 2, u3 entra em pos 3
    r1 = client.post("/reservas", json={"usuario_id": u1["id"], "livro_id": livro["id"]}).json()
    r2 = client.post("/reservas", json={"usuario_id": u2["id"], "livro_id": livro["id"]}).json()
    r3 = client.post("/reservas", json={"usuario_id": u3["id"], "livro_id": livro["id"]}).json()

    assert r1["posicao_na_fila"] == 1
    assert r2["posicao_na_fila"] == 2
    assert r3["posicao_na_fila"] == 3

    # Tentar duplicar reserva para o mesmo usuário no mesmo livro -> 400
    resp_dup = client.post("/reservas", json={"usuario_id": u1["id"], "livro_id": livro["id"]})
    assert resp_dup.status_code == status.HTTP_400_BAD_REQUEST

    # Listar fila do livro
    resp_fila = client.get(f"/reservas/livro/{livro['id']}")
    assert resp_fila.status_code == status.HTTP_200_OK
    fila = resp_fila.json()
    assert len(fila) == 3
    assert [r["usuario_id"] for r in fila] == [u1["id"], u2["id"], u3["id"]]

    # Cancelar a reserva r2 (no meio da fila): r3 deve assumir a posição 2
    resp_canc = client.post(f"/reservas/{r2['id']}/cancelar")
    assert resp_canc.status_code == status.HTTP_200_OK
    assert resp_canc.json()["estado"] == "cancelada"

    # Checar nova ordem da fila: r1 (pos 1), r3 (pos 2)
    resp_fila2 = client.get(f"/reservas/livro/{livro['id']}")
    fila2 = resp_fila2.json()
    assert len(fila2) == 2
    assert fila2[0]["usuario_id"] == u1["id"]
    assert fila2[0]["posicao_na_fila"] == 1
    assert fila2[1]["usuario_id"] == u3["id"]
    assert fila2[1]["posicao_na_fila"] == 2

    # Tentar cancelar novamente -> 400
    resp_canc_dup = client.post(f"/reservas/{r2['id']}/cancelar")
    assert resp_canc_dup.status_code == status.HTTP_400_BAD_REQUEST

    # Reserva inexistente -> 404
    resp_404 = client.post("/reservas/999999/cancelar")
    assert resp_404.status_code == status.HTTP_404_NOT_FOUND
