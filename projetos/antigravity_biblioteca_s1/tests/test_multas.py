def test_multas_listar_e_pagar(client):
    livro = client.post("/livros", json={
        "titulo": "Design Patterns", "autor": "GoF", "isbn": "978-0201633610", "ano": 1994, "area_conhecimento": "Computação"
    }).json()
    ex = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "GOF-01"}).json()

    user = client.post("/usuarios", json={"nome": "Atrasadinho", "email": "atr@gof.com", "matricula": "GOF01", "categoria": "aluno"}).json()["id"]

    # Criar empréstimo
    emp = client.post("/emprestimos", json={
        "usuario_id": user,
        "exemplar_id": ex["id"],
        "data_retirada": "2026-10-01T10:00:00"
    }).json()

    # Devolver com atraso de 4 dias (Aluno: 7 dias prazo, ret 01/10 -> prev 08/10. Dev 12/10 = 4 dias atraso = R$ 4,00)
    client.post(f"/emprestimos/{emp['id']}/devolver", json={"data_devolucao": "2026-10-12T10:00:00"})

    # Listar multas por usuário
    res_multas = client.get(f"/usuarios/{user}/multas")
    assert res_multas.status_code == 200
    multas = res_multas.json()
    assert len(multas) == 1
    multa_id = multas[0]["id"]
    assert multas[0]["estado"] == "aberta"
    assert float(multas[0]["valor"]) == 4.00

    # Pagar multa
    res_pag = client.post(f"/multas/{multa_id}/pagar")
    assert res_pag.status_code == 200
    assert res_pag.json()["estado"] == "paga"
    assert res_pag.json()["data_pagamento"] is not None

    # Tentar pagar novamente -> 400
    res_pag_rep = client.post(f"/multas/{multa_id}/pagar")
    assert res_pag_rep.status_code == 400
    assert "já está paga" in res_pag_rep.json()["detail"].lower()
