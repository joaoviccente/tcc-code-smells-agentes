from datetime import datetime, timedelta
from fastapi import status


def test_relatorios(client):
    hoje = datetime.now()

    # 1. Criar livros em áreas diferentes
    livro_comp = client.post(
        "/livros",
        json={
            "titulo": "Clean Code",
            "autor": "Robert Martin",
            "isbn": "978-0132350884",
            "ano": 2008,
            "area_conhecimento": "Computação",
        },
    ).json()

    livro_mat = client.post(
        "/livros",
        json={
            "titulo": "Álgebra Linear",
            "autor": "Elon Lages",
            "isbn": "978-85-244-0028-1",
            "ano": 2010,
            "area_conhecimento": "Matemática",
        },
    ).json()

    # Criar exemplares
    ex_c1 = client.post(
        "/exemplares",
        json={"livro_id": livro_comp["id"], "codigo_tombo": "CC-01"},
    ).json()
    ex_c2 = client.post(
        "/exemplares",
        json={"livro_id": livro_comp["id"], "codigo_tombo": "CC-02"},
    ).json()

    ex_m1 = client.post(
        "/exemplares",
        json={"livro_id": livro_mat["id"], "codigo_tombo": "AL-01"},
    ).json()

    # Criar usuários
    u1 = client.post(
        "/usuarios",
        json={"nome": "Ana Lima", "email": "ana@test.com", "matricula": "A100", "categoria": "aluno"},
    ).json()
    u2 = client.post(
        "/usuarios",
        json={"nome": "Carlos Reis", "email": "carlos@test.com", "matricula": "A101", "categoria": "aluno"},
    ).json()

    # Empréstimos:
    # Ana pega CC-01 hoje (não está em atraso)
    emp1 = client.post(
        "/emprestimos",
        json={"usuario_id": u1["id"], "exemplar_id": ex_c1["id"], "data_retirada": hoje.isoformat()},
    ).json()

    # Carlos pegou CC-02 há 25 dias e devolveu há 5 dias (atraso de 13 dias)
    ret_carlos = hoje - timedelta(days=25)
    dev_carlos = hoje - timedelta(days=5)
    emp2 = client.post(
        "/emprestimos",
        json={"usuario_id": u2["id"], "exemplar_id": ex_c2["id"], "data_retirada": ret_carlos.isoformat()},
    ).json()
    client.post(
        f"/emprestimos/{emp2['id']}/devolver",
        json={"data_devolucao": dev_carlos.isoformat()},
    )

    # 1. Relatório Livros Mais Emprestados
    d_inicio = (hoje - timedelta(days=30)).isoformat()
    d_fim = (hoje + timedelta(days=1)).isoformat()
    resp_rel_livros = client.get(f"/relatorios/livros-mais-emprestados?data_inicio={d_inicio}&data_fim={d_fim}")
    assert resp_rel_livros.status_code == status.HTTP_200_OK
    rel_livros = resp_rel_livros.json()
    assert len(rel_livros) >= 1
    assert rel_livros[0]["livro_id"] == livro_comp["id"]
    assert rel_livros[0]["total_emprestimos"] == 2

    # 2. Relatório Usuários com Mais Atrasos
    resp_rel_atrasos = client.get("/relatorios/usuarios-mais-atrasos")
    assert resp_rel_atrasos.status_code == status.HTTP_200_OK
    rel_atrasos = resp_rel_atrasos.json()
    assert len(rel_atrasos) == 1
    assert rel_atrasos[0]["usuario_id"] == u2["id"]
    assert rel_atrasos[0]["total_atrasos"] == 1

    # 3. Relatório Taxa de Ocupação do Acervo por Área
    # Em Computação: 2 exemplares ativos, 1 emprestado (CC-01) -> 50%
    # Em Matemática: 1 exemplar ativo, 0 emprestado -> 0%
    resp_rel_taxa = client.get("/relatorios/taxa-ocupacao")
    assert resp_rel_taxa.status_code == status.HTTP_200_OK
    rel_taxa = resp_rel_taxa.json()
    taxa_comp = next((r for r in rel_taxa if r["area_conhecimento"] == "Computação"), None)
    assert taxa_comp is not None
    assert taxa_comp["total_exemplares"] == 2
    assert taxa_comp["exemplares_emprestados"] == 1
    assert taxa_comp["taxa_ocupacao_percentual"] == 50.0

    taxa_mat = next((r for r in rel_taxa if r["area_conhecimento"] == "Matemática"), None)
    assert taxa_mat is not None
    assert taxa_mat["total_exemplares"] == 1
    assert taxa_mat["exemplares_emprestados"] == 0
    assert taxa_mat["taxa_ocupacao_percentual"] == 0.0
