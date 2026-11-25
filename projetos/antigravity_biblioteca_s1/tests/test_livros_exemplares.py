def test_crud_livro(client):
    # Criar
    res = client.post("/livros", json={
        "titulo": "Estruturas de Dados e Algoritmos",
        "autor": "Thomas Cormen",
        "isbn": "978-85-352-3699-6",
        "ano": 2012,
        "area_conhecimento": "Computação"
    })
    assert res.status_code == 201
    livro = res.json()
    assert livro["id"] is not None
    assert livro["titulo"] == "Estruturas de Dados e Algoritmos"

    # Duplicidade ISBN
    res_dup = client.post("/livros", json={
        "titulo": "Outro Livro",
        "autor": "Outro Autor",
        "isbn": "978-85-352-3699-6",
        "ano": 2020,
        "area_conhecimento": "Computação"
    })
    assert res_dup.status_code == 400

    # Atualizar
    res_up = client.put(f"/livros/{livro['id']}", json={
        "ano": 2013
    })
    assert res_up.status_code == 200
    assert res_up.json()["ano"] == 2013

    # Buscar
    res_get = client.get(f"/livros/{livro['id']}")
    assert res_get.status_code == 200

    # Listar por área
    res_list = client.get("/livros?area_conhecimento=Computação")
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

def test_crud_exemplar(client):
    # Criar Livro
    res_livro = client.post("/livros", json={
        "titulo": "Clean Code",
        "autor": "Robert C. Martin",
        "isbn": "978-0132350884",
        "ano": 2008,
        "area_conhecimento": "Engenharia de Software"
    })
    livro_id = res_livro.json()["id"]

    # Criar Exemplar
    res_ex = client.post("/exemplares", json={
        "livro_id": livro_id,
        "codigo_tombo": "TOMBO-001",
        "estado": "disponivel"
    })
    assert res_ex.status_code == 201
    ex = res_ex.json()
    assert ex["codigo_tombo"] == "TOMBO-001"
    assert ex["estado"] == "disponivel"

    # Duplicidade de tombo
    res_dup = client.post("/exemplares", json={
        "livro_id": livro_id,
        "codigo_tombo": "TOMBO-001"
    })
    assert res_dup.status_code == 400

    # Atualizar estado do exemplar
    res_up = client.put(f"/exemplares/{ex['id']}", json={
        "estado": "em_reparo"
    })
    assert res_up.status_code == 200
    assert res_up.json()["estado"] == "em_reparo"

    # Listar exemplares
    res_list = client.get(f"/exemplares?livro_id={livro_id}")
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

    # Deletar exemplar
    res_del = client.delete(f"/exemplares/{ex['id']}")
    assert res_del.status_code == 204
