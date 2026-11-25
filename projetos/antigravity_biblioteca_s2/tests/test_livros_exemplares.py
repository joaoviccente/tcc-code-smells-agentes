def test_crud_livro(client):
    # Criar
    res = client.post(
        "/livros",
        json={
            "titulo": "Estruturas de Dados e Algoritmos",
            "autor": "Thomas Cormen",
            "isbn": "9788535236996",
            "ano": 2012,
            "area_conhecimento": "Computação",
        },
    )
    assert res.status_code == 201
    livro = res.json()
    assert livro["id"] is not None
    assert livro["titulo"] == "Estruturas de Dados e Algoritmos"

    livro_id = livro["id"]

    # Duplicar ISBN
    res_dup = client.post(
        "/livros",
        json={
            "titulo": "Outro Livro",
            "autor": "Outro Autor",
            "isbn": "9788535236996",
            "ano": 2020,
            "area_conhecimento": "Computação",
        },
    )
    assert res_dup.status_code == 409

    # Obter
    res_get = client.get(f"/livros/{livro_id}")
    assert res_get.status_code == 200
    assert res_get.json()["isbn"] == "9788535236996"

    # Atualizar
    res_put = client.put(
        f"/livros/{livro_id}",
        json={"titulo": "Algoritmos: Teoria e Prática"},
    )
    assert res_put.status_code == 200
    assert res_put.json()["titulo"] == "Algoritmos: Teoria e Prática"

    # Listar com filtro
    res_list = client.get("/livros?area_conhecimento=Computação")
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1


def test_crud_exemplar(client):
    # Criar livro base
    res_livro = client.post(
        "/livros",
        json={
            "titulo": "Cálculo I",
            "autor": "James Stewart",
            "isbn": "9788522112586",
            "ano": 2013,
            "area_conhecimento": "Matemática",
        },
    )
    livro_id = res_livro.json()["id"]

    # Criar exemplar
    res_ex = client.post(
        "/exemplares",
        json={
            "livro_id": livro_id,
            "codigo_tombo": "TOMBO-001",
            "estado": "disponivel",
        },
    )
    assert res_ex.status_code == 201
    ex = res_ex.json()
    assert ex["id"] is not None
    assert ex["codigo_tombo"] == "TOMBO-001"
    assert ex["estado"] == "disponivel"
    exemplar_id = ex["id"]

    # Tombo duplicado
    res_dup = client.post(
        "/exemplares",
        json={
            "livro_id": livro_id,
            "codigo_tombo": "TOMBO-001",
        },
    )
    assert res_dup.status_code == 409

    # Atualizar estado para em_reparo
    res_put = client.put(
        f"/exemplares/{exemplar_id}",
        json={"estado": "em_reparo"},
    )
    assert res_put.status_code == 200
    assert res_put.json()["estado"] == "em_reparo"

    # Deletar exemplar
    res_del = client.delete(f"/exemplares/{exemplar_id}")
    assert res_del.status_code == 204

    # Verificar que não existe mais
    res_get = client.get(f"/exemplares/{exemplar_id}")
    assert res_get.status_code == 404
