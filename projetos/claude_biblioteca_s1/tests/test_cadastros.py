def test_crud_usuario(api):
    c = api.c
    u = api.usuario("professor")
    assert u["situacao"] == "ativo" and u["categoria"] == "professor"
    assert api.get(f"/usuarios/{u['id']}")["email"] == u["email"]

    r = c.patch(f"/usuarios/{u['id']}", json={"nome": "Novo Nome"})
    assert r.status_code == 200 and r.json()["nome"] == "Novo Nome"

    r = c.put(f"/usuarios/{u['id']}", json={"nome": "Outro", "email": "outro@uni.br", "matricula": "X123",
                                             "categoria": "aluno"})
    assert r.status_code == 200 and r.json()["categoria"] == "aluno"

    assert len(api.get("/usuarios?categoria=aluno")) == 1
    assert c.delete(f"/usuarios/{u['id']}").status_code == 204
    assert c.get(f"/usuarios/{u['id']}").status_code == 404


def test_validacao_usuario(api):
    c = api.c
    base = {"nome": "Ana", "email": "ana@uni.br", "matricula": "A001", "categoria": "aluno"}
    assert c.post("/usuarios", json=base).status_code == 201
    assert c.post("/usuarios", json={**base, "matricula": "A002"}).status_code == 409  # e-mail duplicado
    assert c.post("/usuarios", json={**base, "email": "b@uni.br"}).status_code == 409  # matricula duplicada
    assert c.post("/usuarios", json={**base, "email": "invalido"}).status_code == 422
    assert c.post("/usuarios", json={**base, "categoria": "reitor"}).status_code == 422
    assert c.post("/usuarios", json={**base, "situacao": "banido"}).status_code == 422
    assert c.post("/usuarios", json={**base, "campo_extra": 1}).status_code == 422
    assert c.post("/usuarios", json={"nome": "Ana"}).status_code == 422


def test_crud_e_validacao_livro(api):
    c = api.c
    corpo = {"titulo": "Algoritmos", "autor": "Cormen", "isbn": "978-0-262-03384-8", "ano": 2009,
             "area": "Computacao"}
    r = c.post("/livros", json=corpo)
    assert r.status_code == 201 and r.json()["isbn"] == "9780262033848"
    livro_id = r.json()["id"]
    assert c.post("/livros", json=corpo).status_code == 409                      # ISBN duplicado
    assert c.post("/livros", json={**corpo, "isbn": "9780262033849"}).status_code == 422  # digito errado
    assert c.post("/livros", json={**corpo, "isbn": "030640615X"}).status_code == 422
    assert c.post("/livros", json={**corpo, "isbn": "0306406152", "ano": 3000}).status_code == 422
    assert c.post("/livros", json={**corpo, "isbn": "0306406152", "titulo": ""}).status_code == 422
    assert c.post("/livros", json={**corpo, "isbn": "0306406152"}).status_code == 201  # ISBN-10 valido

    assert c.patch(f"/livros/{livro_id}", json={"ano": 2010}).json()["ano"] == 2010
    api.exemplar(livro_id)
    assert c.delete(f"/livros/{livro_id}").status_code == 409  # possui exemplares
    assert c.get("/livros/9999").status_code == 404


def test_crud_exemplar(api):
    c = api.c
    livro = api.livro()
    ex = api.exemplar(livro["id"])
    assert ex["estado"] == "disponivel"
    assert c.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": ex["codigo_tombo"]}).status_code == 409
    assert c.post("/exemplares", json={"livro_id": 999, "codigo_tombo": "Z1"}).status_code == 404
    assert c.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "Z2",
                                       "estado": "emprestado"}).status_code == 422
    assert c.patch(f"/exemplares/{ex['id']}", json={"estado": "em_reparo"}).json()["estado"] == "em_reparo"
    assert c.patch(f"/exemplares/{ex['id']}", json={"estado": "reservado"}).status_code == 422
    assert c.patch(f"/exemplares/{ex['id']}", json={"estado": "baixado"}).json()["estado"] == "baixado"
    assert c.patch(f"/exemplares/{ex['id']}", json={"estado": "disponivel"}).status_code == 409
    assert len(api.get(f"/livros/{livro['id']}/exemplares")) == 1
    assert c.delete(f"/exemplares/{ex['id']}").status_code == 204


def test_nao_exclui_usuario_com_historico(api):
    u = api.usuario()
    ex = api.exemplar(api.livro()["id"])
    api.emprestar(u["id"], ex["id"])
    assert api.c.delete(f"/usuarios/{u['id']}").status_code == 409
    assert api.c.delete(f"/exemplares/{ex['id']}").status_code == 409
