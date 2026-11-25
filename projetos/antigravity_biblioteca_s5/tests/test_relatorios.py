from datetime import datetime


def test_relatorios(client):
    # Criar usuários
    u1 = client.post("/usuarios", json={"nome": "User 1", "email": "u1@rel.br", "matricula": "M1-R", "categoria": "aluno"}).json()["id"]
    u2 = client.post("/usuarios", json={"nome": "User 2", "email": "u2@rel.br", "matricula": "M2-R", "categoria": "professor"}).json()["id"]

    # Criar livros em áreas distintas
    l_comp = client.post(
        "/livros",
        json={"titulo": "Python Pro", "autor": "Guido", "isbn": "9781111111110", "ano": 2021, "area_conhecimento": "Computação"},
    ).json()["id"]

    l_mat = client.post(
        "/livros",
        json={"titulo": "Cálculo 1", "autor": "Stewart", "isbn": "9782222222220", "ano": 2019, "area_conhecimento": "Matemática"},
    ).json()["id"]

    # Exemplares
    e_comp1 = client.post("/exemplares", json={"livro_id": l_comp, "codigo_tombo": "TMB-CP-1", "estado": "disponivel"}).json()["id"]
    e_comp2 = client.post("/exemplares", json={"livro_id": l_comp, "codigo_tombo": "TMB-CP-2", "estado": "disponivel"}).json()["id"]
    e_mat1 = client.post("/exemplares", json={"livro_id": l_mat, "codigo_tombo": "TMB-MT-1", "estado": "disponivel"}).json()["id"]

    # Empréstimos em Computação (2 empréstimos)
    d1 = datetime(2026, 5, 1, 10, 0, 0)
    client.post("/emprestimos", json={"usuario_id": u1, "exemplar_id": e_comp1, "data_retirada": d1.isoformat()})
    client.post("/emprestimos", json={"usuario_id": u2, "exemplar_id": e_comp2, "data_retirada": d1.isoformat()})

    # 1. Relatório de Livros Mais Emprestados
    resp_livros = client.get(
        "/relatorios/livros-mais-emprestados?data_inicio=2026-05-01T00:00:00&data_fim=2026-05-31T23:59:59"
    )
    assert resp_livros.status_code == 200
    dados_livros = resp_livros.json()
    assert len(dados_livros) >= 1
    assert dados_livros[0]["livro_id"] == l_comp
    assert dados_livros[0]["total_emprestimos"] == 2

    # 2. Relatório de Taxa de Ocupação por Área
    # Computação: 2 exemplares no total, 2 emprestados -> 100% de ocupação
    # Matemática: 1 exemplar no total, 0 emprestados -> 0% de ocupação
    resp_taxa = client.get("/relatorios/taxa-ocupacao")
    assert resp_taxa.status_code == 200
    dados_taxa = resp_taxa.json()
    mapa_taxas = {item["area_conhecimento"]: item for item in dados_taxa}

    assert "Computação" in mapa_taxas
    assert mapa_taxas["Computação"]["total_exemplares"] == 2
    assert mapa_taxas["Computação"]["exemplares_emprestados"] == 2
    assert mapa_taxas["Computação"]["taxa_ocupacao_percentual"] == 100.0

    assert "Matemática" in mapa_taxas
    assert mapa_taxas["Matemática"]["total_exemplares"] == 1
    assert mapa_taxas["Matemática"]["exemplares_emprestados"] == 0
    assert mapa_taxas["Matemática"]["taxa_ocupacao_percentual"] == 0.0

    # 3. Relatório de Usuários com Mais Atrasos
    # Vamos gerar um atraso para u1 devolvendo após a data prevista
    # Aluno u1 pegou em 2026-05-01, previsto 2026-05-08. Devolve em 2026-05-15 (7 dias de atraso).
    emp_u1 = client.get(f"/emprestimos/usuario/{u1}").json()[0]["id"]
    client.post(
        f"/emprestimos/{emp_u1}/devolver",
        json={"data_devolucao": "2026-05-15T10:00:00"},
    )

    resp_atrasos = client.get("/relatorios/usuarios-mais-atrasos")
    assert resp_atrasos.status_code == 200
    dados_atrasos = resp_atrasos.json()
    assert len(dados_atrasos) >= 1
    assert dados_atrasos[0]["usuario_id"] == u1
    assert dados_atrasos[0]["total_atrasos"] == 1
