from fastapi import status


def test_crud_livro_sucesso(client):
    # Criar
    resp_create = client.post(
        "/livros",
        json={
            "titulo": "Estruturas de Dados e Algoritmos",
            "autor": "Thomas Cormen",
            "isbn": "978-85-352-3699-6",
            "ano": 2012,
            "area_conhecimento": "Ciência da Computação",
        },
    )
    assert resp_create.status_code == status.HTTP_201_CREATED
    livro = resp_create.json()
    assert livro["id"] is not None
    assert livro["titulo"] == "Estruturas de Dados e Algoritmos"
    livro_id = livro["id"]

    # Obter
    resp_get = client.get(f"/livros/{livro_id}")
    assert resp_get.status_code == status.HTTP_200_OK
    assert resp_get.json()["isbn"] == "978-85-352-3699-6"

    # Atualizar
    resp_put = client.put(
        f"/livros/{livro_id}",
        json={"titulo": "Algoritmos: Teoria e Prática"},
    )
    assert resp_put.status_code == status.HTTP_200_OK
    assert resp_put.json()["titulo"] == "Algoritmos: Teoria e Prática"

    # Listar com filtro
    resp_list = client.get("/livros?area_conhecimento=Computação")
    assert resp_list.status_code == status.HTTP_200_OK
    assert len(resp_list.json()) == 1


def test_crud_exemplar_sucesso(client):
    # Criar Livro
    resp_livro = client.post(
        "/livros",
        json={
            "titulo": "Cálculo I",
            "autor": "James Stewart",
            "isbn": "978-85-221-1258-6",
            "ano": 2016,
            "area_conhecimento": "Matemática",
        },
    )
    livro_id = resp_livro.json()["id"]

    # Criar Exemplar
    resp_ex = client.post(
        "/exemplares",
        json={
            "livro_id": livro_id,
            "codigo_tombo": "MAT-001",
            "estado": "disponivel",
        },
    )
    assert resp_ex.status_code == status.HTTP_201_CREATED
    exemplar = resp_ex.json()
    assert exemplar["codigo_tombo"] == "MAT-001"
    assert exemplar["estado"] == "disponivel"
    exemplar_id = exemplar["id"]

    # Tombo duplicado
    resp_dup = client.post(
        "/exemplares",
        json={
            "livro_id": livro_id,
            "codigo_tombo": "MAT-001",
        },
    )
    assert resp_dup.status_code == status.HTTP_409_CONFLICT

    # Atualizar estado
    resp_put = client.put(
        f"/exemplares/{exemplar_id}",
        json={"estado": "em_reparo"},
    )
    assert resp_put.status_code == status.HTTP_200_OK
    assert resp_put.json()["estado"] == "em_reparo"

    # Listar por livro
    resp_list = client.get(f"/livros/{livro_id}/exemplares")
    assert resp_list.status_code == status.HTTP_200_OK
    assert len(resp_list.json()) == 1
    assert resp_list.json()[0]["codigo_tombo"] == "MAT-001"
