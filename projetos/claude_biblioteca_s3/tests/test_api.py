from datetime import timedelta


# ------------------------------------------------------------- CRUD e validacao
def test_crud_usuario(client):
    dados = {"nome": "Ana", "email": "ana@uni.br", "matricula": "2024001", "categoria": "aluno"}
    r = client.post("/usuarios", json=dados)
    assert r.status_code == 201
    u = r.json()
    assert u["situacao"] == "ativo"
    assert client.post("/usuarios", json=dados).status_code == 409  # duplicado
    assert client.get(f"/usuarios/{u['id']}").status_code == 200
    r = client.patch(f"/usuarios/{u['id']}", json={"categoria": "professor"})
    assert r.status_code == 200 and r.json()["categoria"] == "professor"
    assert client.delete(f"/usuarios/{u['id']}").status_code == 204
    assert client.get(f"/usuarios/{u['id']}").status_code == 404


def test_validacao_usuario(client):
    base = {"nome": "Ana", "email": "ana@uni.br", "matricula": "1", "categoria": "aluno"}
    assert client.post("/usuarios", json={**base, "email": "invalido"}).status_code == 422
    assert client.post("/usuarios", json={**base, "categoria": "funcionario"}).status_code == 422
    assert client.post("/usuarios", json={**base, "nome": "  "}).status_code == 422
    assert client.post("/usuarios", json={**base, "extra": 1}).status_code == 422
    assert client.post("/usuarios", json={"nome": "Ana"}).status_code == 422


def test_crud_livro_e_isbn(client):
    base = {"titulo": "Algoritmos", "autor": "Cormen", "isbn": "978-0-262-03384-8", "ano": 2009,
            "area": "Computacao"}
    r = client.post("/livros", json=base)
    assert r.status_code == 201 and r.json()["isbn"] == "9780262033848"
    assert client.post("/livros", json=base).status_code == 409
    assert client.post("/livros", json={**base, "isbn": "9780262033840"}).status_code == 422
    assert client.post("/livros", json={**base, "isbn": "0-306-40615-2"}).status_code == 201  # ISBN-10
    assert client.post("/livros", json={**base, "isbn": "9780306406157", "ano": 3000}).status_code == 422
    livro = r.json()
    r = client.put(f"/livros/{livro['id']}", json={"titulo": "Algoritmos 3a ed"})
    assert r.status_code == 200 and r.json()["titulo"] == "Algoritmos 3a ed"
    client.post("/exemplares", json={"livro_id": livro["id"], "tombo": "X1"})
    assert client.delete(f"/livros/{livro['id']}").status_code == 409


def test_crud_exemplar(client, fabrica):
    livro = fabrica.livro()
    assert client.post("/exemplares", json={"livro_id": 999, "tombo": "A"}).status_code == 404
    r = client.post("/exemplares", json={"livro_id": livro["id"], "tombo": "A-1"})
    assert r.status_code == 201 and r.json()["estado"] == "disponivel"
    ex = r.json()
    assert client.post("/exemplares", json={"livro_id": livro["id"], "tombo": "A-1"}).status_code == 409
    assert client.post("/exemplares", json={"livro_id": livro["id"], "tombo": "B",
                                            "estado": "emprestado"}).status_code == 422
    assert client.patch(f"/exemplares/{ex['id']}", json={"estado": "reservado"}).status_code == 409
    assert client.patch(f"/exemplares/{ex['id']}", json={"estado": "xyz"}).status_code == 422
    assert len(fabrica.get(f"/livros/{livro['id']}/exemplares")) == 1
    assert client.delete(f"/exemplares/{ex['id']}").status_code == 204


def test_not_found_e_devolucao_dupla(client, fabrica):
    assert client.post("/emprestimos", json={"usuario_id": 1, "exemplar_id": 1}).status_code == 404
    assert client.post("/emprestimos/99/devolucao").status_code == 404
    assert client.post("/multas/99/pagamento").status_code == 404
    assert client.get("/livros/99/reservas").status_code == 404
    u = fabrica.usuario()
    ex = fabrica.exemplar(fabrica.livro()["id"])
    emp = fabrica.emprestar(u["id"], ex["id"])
    fabrica.devolver(emp["id"])
    assert client.post(f"/emprestimos/{emp['id']}/devolucao").status_code == 409
    assert client.post(f"/emprestimos/{emp['id']}/renovacao").status_code == 409
    assert len(fabrica.get(f"/usuarios/{u['id']}/emprestimos")) == 1


# ------------------------------------------------------------- relatorios
def test_relatorios(client, fabrica, relogio):
    u1, u2 = fabrica.usuario("professor"), fabrica.usuario("professor")
    l1 = fabrica.livro(area="Computacao")
    l2 = fabrica.livro(area="Direito")
    e1a, e1b = fabrica.exemplar(l1["id"]), fabrica.exemplar(l1["id"])
    e2 = fabrica.exemplar(l2["id"])
    fabrica.exemplar(l2["id"], estado="baixado")
    fabrica.exemplar(l2["id"], estado="em_reparo")

    hoje = relogio.atual.date()
    emp1 = fabrica.emprestar(u1["id"], e1a["id"])
    fabrica.emprestar(u2["id"], e1b["id"])
    emp3 = fabrica.emprestar(u1["id"], e2["id"])

    r = fabrica.get(f"/relatorios/livros-mais-emprestados?inicio={hoje}&fim={hoje}")
    assert [(x["livro_id"], x["total_emprestimos"]) for x in r] == [(l1["id"], 2), (l2["id"], 1)]
    amanha = hoje + timedelta(days=1)
    assert fabrica.get(f"/relatorios/livros-mais-emprestados?inicio={amanha}&fim={amanha}") == []
    assert client.get(f"/relatorios/livros-mais-emprestados?inicio={amanha}&fim={hoje}").status_code == 422
    assert client.get("/relatorios/livros-mais-emprestados").status_code == 422

    ocup = {o["area"]: o for o in fabrica.get("/relatorios/ocupacao-por-area")}
    assert ocup["Computacao"]["taxa_ocupacao"] == 1.0
    assert ocup["Direito"]["total_exemplares"] == 2  # baixado fora do acervo ativo
    assert ocup["Direito"]["taxa_ocupacao"] == 0.5

    relogio.avancar(dias=35)
    fabrica.devolver(emp1["id"])
    atrasos = fabrica.get("/relatorios/usuarios-com-mais-atrasos")
    assert atrasos[0]["usuario_id"] == u1["id"]
    assert atrasos[0]["emprestimos_atrasados"] == 2
    assert atrasos[0]["total_dias_atraso"] == 10
    assert atrasos[1]["usuario_id"] == u2["id"]
    assert emp3["id"]
