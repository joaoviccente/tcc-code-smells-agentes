from datetime import datetime, timedelta, timezone


def criar_livro_e_exemplar(client, tombo="TOMBO-TESTE", estado="disponivel"):
    res_livro = client.post(
        "/livros",
        json={
            "titulo": f"Livro {tombo}",
            "autor": "Autor Teste",
            "isbn": f"ISBN-{tombo}",
            "ano": 2022,
            "area_conhecimento": "Geral",
        },
    )
    livro_id = res_livro.json()["id"]
    res_ex = client.post(
        "/exemplares",
        json={"livro_id": livro_id, "codigo_tombo": tombo, "estado": estado},
    )
    return livro_id, res_ex.json()["id"]


def test_regras_categoria_aluno(client):
    # Aluno: limite 3, prazo 7 dias, 2 renovações
    res_u = client.post(
        "/usuarios",
        json={
            "nome": "Aluno Teste",
            "email": "aluno@teste.com",
            "matricula": "A001",
            "categoria": "aluno",
        },
    )
    user_id = res_u.json()["id"]

    _, ex1 = criar_livro_e_exemplar(client, "ALU-1")
    _, ex2 = criar_livro_e_exemplar(client, "ALU-2")
    _, ex3 = criar_livro_e_exemplar(client, "ALU-3")
    _, ex4 = criar_livro_e_exemplar(client, "ALU-4")

    agora = datetime.now(timezone.utc)
    res_emp1 = client.post(
        "/emprestimos",
        json={"usuario_id": user_id, "exemplar_id": ex1, "data_retirada": agora.isoformat()},
    )
    assert res_emp1.status_code == 201
    emp1 = res_emp1.json()
    # Prazo de 7 dias
    prevista1 = datetime.fromisoformat(emp1["data_prevista"])
    retirada1 = datetime.fromisoformat(emp1["data_retirada"])
    assert (prevista1.date() - retirada1.date()).days == 7

    # 2º e 3º empréstimos dentro do limite de 3
    assert client.post("/emprestimos", json={"usuario_id": user_id, "exemplar_id": ex2}).status_code == 201
    assert client.post("/emprestimos", json={"usuario_id": user_id, "exemplar_id": ex3}).status_code == 201

    # 4º empréstimo deve ser negado (limite atingido)
    res_emp4 = client.post("/emprestimos", json={"usuario_id": user_id, "exemplar_id": ex4})
    assert res_emp4.status_code == 400
    assert "limite de 3" in res_emp4.json()["detail"].lower()

    # Teste de renovações do Aluno: 2 permitidas
    emp1_id = emp1["id"]
    # 1ª renovação
    res_renov1 = client.post(f"/emprestimos/{emp1_id}/renovar")
    assert res_renov1.status_code == 200
    assert res_renov1.json()["numero_renovacoes"] == 1
    # 2ª renovação
    res_renov2 = client.post(f"/emprestimos/{emp1_id}/renovar")
    assert res_renov2.status_code == 200
    assert res_renov2.json()["numero_renovacoes"] == 2
    # 3ª renovação deve ser negada
    res_renov3 = client.post(f"/emprestimos/{emp1_id}/renovar")
    assert res_renov3.status_code == 400
    assert "limite de 2 renovações" in res_renov3.json()["detail"].lower()


def test_regras_categoria_professor(client):
    # Professor: limite 8, prazo 30 dias, 4 renovações
    res_u = client.post(
        "/usuarios",
        json={
            "nome": "Professor Teste",
            "email": "prof@teste.com",
            "matricula": "P001",
            "categoria": "professor",
        },
    )
    user_id = res_u.json()["id"]

    _, ex1 = criar_livro_e_exemplar(client, "PROF-1")
    agora = datetime.now(timezone.utc)
    res_emp = client.post(
        "/emprestimos",
        json={"usuario_id": user_id, "exemplar_id": ex1, "data_retirada": agora.isoformat()},
    )
    assert res_emp.status_code == 201
    emp = res_emp.json()
    prevista = datetime.fromisoformat(emp["data_prevista"])
    retirada = datetime.fromisoformat(emp["data_retirada"])
    assert (prevista.date() - retirada.date()).days == 30

    emp_id = emp["id"]
    # 4 renovações permitidas
    for i in range(1, 5):
        r = client.post(f"/emprestimos/{emp_id}/renovar")
        assert r.status_code == 200
        assert r.json()["numero_renovacoes"] == i

    # 5ª renovação negada
    r5 = client.post(f"/emprestimos/{emp_id}/renovar")
    assert r5.status_code == 400
    assert "limite de 4 renovações" in r5.json()["detail"].lower()


def test_regras_categoria_visitante(client):
    # Visitante: limite 1, prazo 3 dias, 0 renovações
    res_u = client.post(
        "/usuarios",
        json={
            "nome": "Visitante Teste",
            "email": "vis@teste.com",
            "matricula": "V001",
            "categoria": "visitante",
        },
    )
    user_id = res_u.json()["id"]

    _, ex1 = criar_livro_e_exemplar(client, "VIS-1")
    _, ex2 = criar_livro_e_exemplar(client, "VIS-2")

    agora = datetime.now(timezone.utc)
    res_emp = client.post(
        "/emprestimos",
        json={"usuario_id": user_id, "exemplar_id": ex1, "data_retirada": agora.isoformat()},
    )
    assert res_emp.status_code == 201
    emp = res_emp.json()
    prevista = datetime.fromisoformat(emp["data_prevista"])
    retirada = datetime.fromisoformat(emp["data_retirada"])
    assert (prevista.date() - retirada.date()).days == 3

    # Segundo empréstimo negado (limite 1)
    res_emp2 = client.post("/emprestimos", json={"usuario_id": user_id, "exemplar_id": ex2})
    assert res_emp2.status_code == 400
    assert "limite de 1" in res_emp2.json()["detail"].lower()

    # Nenhuma renovação permitida
    res_renov = client.post(f"/emprestimos/{emp['id']}/renovar")
    assert res_renov.status_code == 400
    assert "limite de 0 renovações" in res_renov.json()["detail"].lower()


def test_exemplar_em_reparo_ou_baixado(client):
    res_u = client.post(
        "/usuarios",
        json={
            "nome": "Aluno Teste 2",
            "email": "aluno2@teste.com",
            "matricula": "A002",
            "categoria": "aluno",
        },
    )
    user_id = res_u.json()["id"]

    _, ex_rep = criar_livro_e_exemplar(client, "REP-1", estado="em_reparo")
    _, ex_bx = criar_livro_e_exemplar(client, "BX-1", estado="baixado")

    r_rep = client.post("/emprestimos", json={"usuario_id": user_id, "exemplar_id": ex_rep})
    assert r_rep.status_code == 400
    assert "em_reparo" in r_rep.json()["detail"]

    r_bx = client.post("/emprestimos", json={"usuario_id": user_id, "exemplar_id": ex_bx})
    assert r_bx.status_code == 400
    assert "baixado" in r_bx.json()["detail"]


def test_renovacao_negada_com_fila_reserva(client):
    # Criar livro e exemplar
    livro_id, ex_id = criar_livro_e_exemplar(client, "RES-TESTE")

    # Criar 2 usuários
    u1 = client.post(
        "/usuarios",
        json={"nome": "U1", "email": "u1@teste.com", "matricula": "U01", "categoria": "aluno"},
    ).json()["id"]
    u2 = client.post(
        "/usuarios",
        json={"nome": "U2", "email": "u2@teste.com", "matricula": "U02", "categoria": "aluno"},
    ).json()["id"]

    # U1 empresta o exemplar
    emp = client.post(
        "/emprestimos",
        json={"usuario_id": u1, "exemplar_id": ex_id},
    ).json()

    # U2 faz reserva do livro
    res_r = client.post(
        "/reservas",
        json={"livro_id": livro_id, "usuario_id": u2},
    )
    assert res_r.status_code == 201

    # U1 tenta renovar: deve ser negado porque há reserva na fila
    r_renov = client.post(f"/emprestimos/{emp['id']}/renovar")
    assert r_renov.status_code == 400
    assert "fila de reserva" in r_renov.json()["detail"].lower()


def test_renovacao_negada_se_atrasado(client):
    _, ex_id = criar_livro_e_exemplar(client, "ATR-TESTE")
    u1 = client.post(
        "/usuarios",
        json={"nome": "U3", "email": "u3@teste.com", "matricula": "U03", "categoria": "aluno"},
    ).json()["id"]

    # Retirada há 10 dias atrás (prazo de aluno é 7 dias, logo está 3 dias atrasado)
    agora = datetime.now(timezone.utc)
    retirada = agora - timedelta(days=10)

    emp = client.post(
        "/emprestimos",
        json={"usuario_id": u1, "exemplar_id": ex_id, "data_retirada": retirada.isoformat()},
    ).json()

    # Tentativa de renovação na data atual (atrasado)
    res_renov = client.post(
        f"/emprestimos/{emp['id']}/renovar",
        json={"data_renovacao": agora.isoformat()},
    )
    assert res_renov.status_code == 400
    assert "atrasado" in res_renov.json()["detail"].lower()
