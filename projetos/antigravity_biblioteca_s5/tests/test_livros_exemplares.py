def test_crud_livro_sucesso(client):
    # Criar
    resp = client.post(
        "/livros",
        json={
            "titulo": "Clean Code",
            "autor": "Robert C. Martin",
            "isbn": "9780132350884",
            "ano": 2008,
            "area_conhecimento": "Engenharia de Software",
        },
    )
    assert resp.status_code == 201
    livro_id = resp.json()["id"]

    # Obter
    get_resp = client.get(f"/livros/{livro_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["titulo"] == "Clean Code"

    # Atualizar
    put_resp = client.put(f"/livros/{livro_id}", json={"ano": 2009})
    assert put_resp.status_code == 200
    assert put_resp.json()["ano"] == 2009

    # Deletar
    del_resp = client.delete(f"/livros/{livro_id}")
    assert del_resp.status_code == 204


def test_criar_livro_isbn_duplicado(client):
    client.post(
        "/livros",
        json={
            "titulo": "Livro 1",
            "autor": "Autor 1",
            "isbn": "9781234567890",
            "ano": 2020,
            "area_conhecimento": "Exatas",
        },
    )
    resp = client.post(
        "/livros",
        json={
            "titulo": "Livro 2",
            "autor": "Autor 2",
            "isbn": "9781234567890",
            "ano": 2021,
            "area_conhecimento": "Humanas",
        },
    )
    assert resp.status_code == 409


def test_crud_exemplar_sucesso(client):
    # Criar Livro
    l_resp = client.post(
        "/livros",
        json={
            "titulo": "Design Patterns",
            "autor": "GoF",
            "isbn": "9780201633610",
            "ano": 1994,
            "area_conhecimento": "Computação",
        },
    )
    livro_id = l_resp.json()["id"]

    # Criar Exemplar
    e_resp = client.post(
        "/exemplares",
        json={
            "livro_id": livro_id,
            "codigo_tombo": "TMB-DP-01",
            "estado": "disponivel",
        },
    )
    assert e_resp.status_code == 201
    exemplar_id = e_resp.json()["id"]
    assert e_resp.json()["estado"] == "disponivel"

    # Atualizar estado para em_reparo
    put_resp = client.put(
        f"/exemplares/{exemplar_id}",
        json={"estado": "em_reparo"},
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["estado"] == "em_reparo"

    # Deletar exemplar
    del_resp = client.delete(f"/exemplares/{exemplar_id}")
    assert del_resp.status_code == 204


def test_codigo_tombo_duplicado(client):
    l_resp = client.post(
        "/livros",
        json={
            "titulo": "Livro",
            "autor": "Autor",
            "isbn": "9780000000001",
            "ano": 2020,
            "area_conhecimento": "Geral",
        },
    )
    livro_id = l_resp.json()["id"]

    client.post(
        "/exemplares",
        json={"livro_id": livro_id, "codigo_tombo": "TMB-DUP", "estado": "disponivel"},
    )
    resp = client.post(
        "/exemplares",
        json={"livro_id": livro_id, "codigo_tombo": "TMB-DUP", "estado": "disponivel"},
    )
    assert resp.status_code == 409


def test_regra_6_cancelamento_reservas_ao_baixar_ultimo_exemplar(client):
    # Cria livro
    l_resp = client.post(
        "/livros",
        json={
            "titulo": "Livro Raro",
            "autor": "Autor Raro",
            "isbn": "9789999999999",
            "ano": 1950,
            "area_conhecimento": "História",
        },
    )
    livro_id = l_resp.json()["id"]

    # Cria apenas 1 exemplar
    e_resp = client.post(
        "/exemplares",
        json={"livro_id": livro_id, "codigo_tombo": "TMB-RARO-1", "estado": "disponivel"},
    )
    exemplar_id = e_resp.json()["id"]

    # Cria usuário e reserva
    u_resp = client.post(
        "/usuarios",
        json={"nome": "Aluno Fila", "email": "fila@uni.br", "matricula": "M-FILA", "categoria": "aluno"},
    )
    usuario_id = u_resp.json()["id"]

    res_resp = client.post(
        "/reservas",
        json={"livro_id": livro_id, "usuario_id": usuario_id},
    )
    assert res_resp.status_code == 201
    reserva_id = res_resp.json()["id"]

    # Baixa o único exemplar
    client.put(f"/exemplares/{exemplar_id}", json={"estado": "baixado"})

    # Verifica se a reserva do livro foi automaticamente cancelada (Regra 6)
    fila_resp = client.get(f"/reservas/livro/{livro_id}")
    assert fila_resp.status_code == 200
    assert len(fila_resp.json()) == 0  # Não há mais reservas ativas na fila
