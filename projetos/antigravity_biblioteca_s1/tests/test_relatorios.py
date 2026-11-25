def test_relatorios(client):
    # Criar 2 livros em áreas diferentes
    l1 = client.post("/livros", json={
        "titulo": "Python Fluente", "autor": "Luciano Ramalho", "isbn": "978-8575224625", "ano": 2015, "area_conhecimento": "Computação"
    }).json()

    l2 = client.post("/livros", json={
        "titulo": "Microeconomia", "autor": "Pindyck", "isbn": "978-8576058137", "ano": 2013, "area_conhecimento": "Economia"
    }).json()

    # Exemplares
    ex1_l1 = client.post("/exemplares", json={"livro_id": l1["id"], "codigo_tombo": "PY-01"}).json()
    ex2_l1 = client.post("/exemplares", json={"livro_id": l1["id"], "codigo_tombo": "PY-02"}).json()
    ex1_l2 = client.post("/exemplares", json={"livro_id": l2["id"], "codigo_tombo": "ECON-01"}).json()

    # Usuários
    u1 = client.post("/usuarios", json={"nome": "User 1", "email": "u1@rel.com", "matricula": "REL01", "categoria": "aluno"}).json()["id"]
    u2 = client.post("/usuarios", json={"nome": "User 2", "email": "u2@rel.com", "matricula": "REL02", "categoria": "aluno"}).json()["id"]

    # Empréstimos:
    # l1 emprestado 2 vezes (1 por u1, 1 por u2)
    emp1 = client.post("/emprestimos", json={"usuario_id": u1, "exemplar_id": ex1_l1["id"], "data_retirada": "2026-05-01T10:00:00"}).json()
    emp2 = client.post("/emprestimos", json={"usuario_id": u2, "exemplar_id": ex2_l1["id"], "data_retirada": "2026-05-02T10:00:00"}).json()

    # u1 devolve com atraso
    client.post(f"/emprestimos/{emp1['id']}/devolver", json={"data_devolucao": "2026-05-20T10:00:00"})

    # 1. Relatório: Livros mais emprestados
    res_livros = client.get("/relatorios/livros-mais-emprestados?data_inicio=2026-05-01T00:00:00&data_fim=2026-05-31T23:59:59")
    assert res_livros.status_code == 200
    dados_livros = res_livros.json()
    assert len(dados_livros) >= 1
    assert dados_livros[0]["livro_id"] == l1["id"]
    assert dados_livros[0]["total_emprestimos"] == 2

    # 2. Relatório: Usuários com mais atrasos
    res_atrasos = client.get("/relatorios/usuarios-mais-atrasos")
    assert res_atrasos.status_code == 200
    dados_atrasos = res_atrasos.json()
    assert len(dados_atrasos) >= 1
    assert dados_atrasos[0]["usuario_id"] == u1
    assert dados_atrasos[0]["total_atrasos"] == 1

    # 3. Relatório: Taxa de ocupação por área
    res_ocup = client.get("/relatorios/taxa-ocupacao-acervo")
    assert res_ocup.status_code == 200
    dados_ocup = res_ocup.json()
    # Computação tem 2 exemplares, 1 ainda emprestado (emp2) -> taxa = 50.0%
    comp = next(item for item in dados_ocup if item["area_conhecimento"] == "Computação")
    assert comp["total_exemplares"] == 2
    assert comp["exemplares_emprestados"] == 1
    assert comp["taxa_ocupacao"] == 50.0
