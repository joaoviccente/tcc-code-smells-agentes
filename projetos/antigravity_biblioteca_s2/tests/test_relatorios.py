from datetime import datetime, timedelta, timezone


def test_relatorios_completos(client):
    # Criar livros em áreas diferentes
    l1 = client.post(
        "/livros",
        json={"titulo": "Python Fluente", "autor": "Luciano Ramalho", "isbn": "ISBN-L1", "ano": 2021, "area_conhecimento": "Computação"},
    ).json()["id"]

    l2 = client.post(
        "/livros",
        json={"titulo": "Física Básica", "autor": "Halliday", "isbn": "ISBN-L2", "ano": 2018, "area_conhecimento": "Física"},
    ).json()["id"]

    # Criar exemplares
    ex1_1 = client.post("/exemplares", json={"livro_id": l1, "codigo_tombo": "PY-1"}).json()["id"]
    ex1_2 = client.post("/exemplares", json={"livro_id": l1, "codigo_tombo": "PY-2"}).json()["id"]
    ex2_1 = client.post("/exemplares", json={"livro_id": l2, "codigo_tombo": "FIS-1"}).json()["id"]

    # Criar usuários
    u1 = client.post(
        "/usuarios",
        json={"nome": "User 1", "email": "u1_rel@teste.com", "matricula": "REL01", "categoria": "aluno"},
    ).json()["id"]
    u2 = client.post(
        "/usuarios",
        json={"nome": "User 2", "email": "u2_rel@teste.com", "matricula": "REL02", "categoria": "aluno"},
    ).json()["id"]

    agora = datetime.now(timezone.utc)
    # 2 empréstimos para o Livro 1
    emp1 = client.post(
        "/emprestimos",
        json={"usuario_id": u1, "exemplar_id": ex1_1, "data_retirada": (agora - timedelta(days=20)).isoformat()},
    ).json()
    emp2 = client.post(
        "/emprestimos",
        json={"usuario_id": u2, "exemplar_id": ex1_2, "data_retirada": (agora - timedelta(days=5)).isoformat()},
    ).json()

    # Devolver emp1 com atraso (prazo era 7 dias, retirado há 20 dias -> 13 dias atraso)
    client.post(
        f"/emprestimos/{emp1['id']}/devolver",
        json={"data_devolucao": agora.isoformat()},
    )

    # 1. Relatório: Livros mais emprestados
    res_mais_emp = client.get("/relatorios/livros-mais-emprestados")
    assert res_mais_emp.status_code == 200
    dados_mais_emp = res_mais_emp.json()
    assert len(dados_mais_emp) >= 1
    assert dados_mais_emp[0]["livro_id"] == l1
    assert dados_mais_emp[0]["total_emprestimos"] == 2

    # 2. Relatório: Usuários com mais atrasos
    res_atrasos = client.get("/relatorios/usuarios-mais-atrasos")
    assert res_atrasos.status_code == 200
    dados_atrasos = res_atrasos.json()
    assert len(dados_atrasos) >= 1
    # u1 deve liderar pois teve 1 atraso de 13 dias
    assert dados_atrasos[0]["usuario_id"] == u1
    assert dados_atrasos[0]["total_atrasos"] == 1
    assert dados_atrasos[0]["total_dias_atraso"] == 13

    # 3. Relatório: Taxa de ocupação por área
    # Computação: 2 exemplares (ex1_1 devolvido, ex1_2 emprestado) -> 1/2 = 50%
    # Física: 1 exemplar (ex2_1 disponível) -> 0/1 = 0%
    res_taxa = client.get("/relatorios/taxa-ocupacao")
    assert res_taxa.status_code == 200
    dados_taxa = res_taxa.json()
    assert len(dados_taxa) == 2

    computacao = next(d for d in dados_taxa if d["area_conhecimento"] == "Computação")
    assert computacao["total_exemplares"] == 2
    assert computacao["exemplares_emprestados"] == 1
    assert computacao["taxa_ocupacao_percentual"] == 50.0

    fisica = next(d for d in dados_taxa if d["area_conhecimento"] == "Física")
    assert fisica["total_exemplares"] == 1
    assert fisica["exemplares_emprestados"] == 0
    assert fisica["taxa_ocupacao_percentual"] == 0.0
