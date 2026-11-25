def test_crud_livro(client):
    # 1. Criar livro
    payload = {
        "titulo": "Estruturas de Dados e Algoritmos",
        "autor": "Thomas Cormen",
        "isbn": "978-85-352-3699-6",
        "ano": 2012,
        "area": "Ciência da Computação"
    }
    response = client.post("/livros", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["titulo"] == payload["titulo"]
    assert data["isbn"] == payload["isbn"]

    livro_id = data["id"]

    # 2. Obter por ID
    get_res = client.get(f"/livros/{livro_id}")
    assert get_res.status_code == 200
    assert get_res.json()["titulo"] == payload["titulo"]

    # 3. Listar livros com filtro de área
    list_res = client.get("/livros?area=Computação")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    # 4. Atualizar livro
    put_res = client.put(f"/livros/{livro_id}", json={"ano": 2013})
    assert put_res.status_code == 200
    assert put_res.json()["ano"] == 2013

    # 5. Excluir livro
    del_res = client.delete(f"/livros/{livro_id}")
    assert del_res.status_code == 204
    assert client.get(f"/livros/{livro_id}").status_code == 404


def test_duplicidade_isbn(client):
    payload = {
        "titulo": "Clean Code",
        "autor": "Robert Martin",
        "isbn": "9780132350884",
        "ano": 2008,
        "area": "Engenharia de Software"
    }
    client.post("/livros", json=payload)

    # Tentativa de criar com mesmo ISBN
    res = client.post("/livros", json=payload)
    assert res.status_code == 409
