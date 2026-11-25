def test_crud_exemplar(client):
    # Criar livro base
    livro = client.post("/livros", json={
        "titulo": "Sistemas Operacionais Modernos",
        "autor": "Andrew Tanenbaum",
        "isbn": "978-85-430-0567-6",
        "ano": 2016,
        "area": "Sistemas Operacionais"
    }).json()

    # 1. Criar exemplar
    payload = {
        "livro_id": livro["id"],
        "codigo_tombo": "TOMBO-001",
        "estado": "disponivel"
    }
    response = client.post("/exemplares", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["codigo_tombo"] == "TOMBO-001"
    assert data["estado"] == "disponivel"

    exemplar_id = data["id"]

    # 2. Obter por ID
    get_res = client.get(f"/exemplares/{exemplar_id}")
    assert get_res.status_code == 200
    assert get_res.json()["codigo_tombo"] == "TOMBO-001"

    # 3. Listar por livro_id
    list_res = client.get(f"/exemplares?livro_id={livro['id']}")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    # 4. Atualizar estado para em_reparo
    put_res = client.put(f"/exemplares/{exemplar_id}", json={"estado": "em_reparo"})
    assert put_res.status_code == 200
    assert put_res.json()["estado"] == "em_reparo"

    # 5. Excluir exemplar
    del_res = client.delete(f"/exemplares/{exemplar_id}")
    assert del_res.status_code == 204
    assert client.get(f"/exemplares/{exemplar_id}").status_code == 404


def test_duplicidade_codigo_tombo(client):
    livro = client.post("/livros", json={
        "titulo": "Redes de Computadores",
        "autor": "Andrew Tanenbaum",
        "isbn": "978-85-7605-924-0",
        "ano": 2011,
        "area": "Redes"
    }).json()

    client.post("/exemplares", json={
        "livro_id": livro["id"],
        "codigo_tombo": "TOMBO-REDES-1"
    })

    res = client.post("/exemplares", json={
        "livro_id": livro["id"],
        "codigo_tombo": "TOMBO-REDES-1"
    })
    assert res.status_code == 409
