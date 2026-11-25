def test_reservas_fila_e_cancelamento(client):
    livro = client.post("/livros", json={
        "titulo": "Algoritmos", "autor": "Sedgewick", "isbn": "978-0321573513", "ano": 2011, "area_conhecimento": "Computação"
    }).json()
    ex = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "SEDG-01"}).json()

    u1 = client.post("/usuarios", json={"nome": "A1", "email": "a1@test.org", "matricula": "M1", "categoria": "aluno"}).json()["id"]
    u2 = client.post("/usuarios", json={"nome": "A2", "email": "a2@test.org", "matricula": "M2", "categoria": "aluno"}).json()["id"]

    # Cria empréstimo com u1
    client.post("/emprestimos", json={"usuario_id": u1, "exemplar_id": ex["id"]})

    # u2 cria reserva
    res_r = client.post("/reservas", json={"usuario_id": u2, "livro_id": livro["id"]})
    assert res_r.status_code == 201
    reserva_id = res_r.json()["id"]
    assert res_r.json()["posicao_fila"] == 1

    # Listar fila do livro
    res_fila = client.get(f"/livros/{livro['id']}/reservas")
    assert res_fila.status_code == 200
    assert len(res_fila.json()) == 1
    assert res_fila.json()[0]["id"] == reserva_id

    # Cancelar reserva
    res_canc = client.post(f"/reservas/{reserva_id}/cancelar")
    assert res_canc.status_code == 200
    assert res_canc.json()["estado"] == "cancelada"

    # Fila vazia agora
    res_fila2 = client.get(f"/livros/{livro['id']}/reservas")
    assert len(res_fila2.json()) == 0
