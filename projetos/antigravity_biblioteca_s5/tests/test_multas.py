from datetime import datetime, timedelta


def test_regra_5_multa_professor_perdao_ate_2_dias(client):
    # Professor tem prazo de 30 dias.
    u_resp = client.post("/usuarios", json={"nome": "Prof Pardoned", "email": "prof_p@u.br", "matricula": "MPP", "categoria": "professor"})
    u_id = u_resp.json()["id"]

    l_resp = client.post("/livros", json={"titulo": "Física", "autor": "Halliday", "isbn": "9788521630357", "ano": 2016, "area_conhecimento": "Física"})
    l_id = l_resp.json()["id"]

    e_resp = client.post("/exemplares", json={"livro_id": l_id, "codigo_tombo": "TMB-FIS-1", "estado": "disponivel"})
    e_id = e_resp.json()["id"]

    # Retirada em 2026-01-01 -> Previsto 2026-01-31 (30 dias)
    data_retirada = datetime(2026, 1, 1, 10, 0, 0)
    emp_id = client.post("/emprestimos", json={"usuario_id": u_id, "exemplar_id": e_id, "data_retirada": data_retirada.isoformat()}).json()["id"]

    # Devolução com 2 dias de atraso (2026-02-02) -> Multa deve ser perdoada automaticamente (Regra 5)
    data_devolucao = datetime(2026, 2, 2, 10, 0, 0)
    client.post(f"/emprestimos/{emp_id}/devolver", json={"data_devolucao": data_devolucao.isoformat()})

    multas = client.get(f"/multas/usuario/{u_id}").json()
    assert len(multas) == 1
    assert multas[0]["estado"] == "perdoada"
    assert float(multas[0]["valor"]) == 1.00  # 2 dias * R$ 0,50


def test_regra_5_multa_professor_atraso_3_dias_aberta(client):
    u_resp = client.post("/usuarios", json={"nome": "Prof Fine", "email": "prof_f@u.br", "matricula": "MPF", "categoria": "professor"})
    u_id = u_resp.json()["id"]

    l_resp = client.post("/livros", json={"titulo": "Química", "autor": "Atkins", "isbn": "9788540701540", "ano": 2018, "area_conhecimento": "Química"})
    l_id = l_resp.json()["id"]

    e_resp = client.post("/exemplares", json={"livro_id": l_id, "codigo_tombo": "TMB-QUI-1", "estado": "disponivel"})
    e_id = e_resp.json()["id"]

    # Retirada 2026-01-01 -> Previsto 2026-01-31. Devolução com 3 dias de atraso (2026-02-03)
    data_retirada = datetime(2026, 1, 1, 10, 0, 0)
    emp_id = client.post("/emprestimos", json={"usuario_id": u_id, "exemplar_id": e_id, "data_retirada": data_retirada.isoformat()}).json()["id"]

    data_devolucao = datetime(2026, 2, 3, 10, 0, 0)
    client.post(f"/emprestimos/{emp_id}/devolver", json={"data_devolucao": data_devolucao.isoformat()})

    multas = client.get(f"/multas/usuario/{u_id}").json()
    assert len(multas) == 1
    assert multas[0]["estado"] == "aberta"
    assert float(multas[0]["valor"]) == 1.50  # 3 dias * R$ 0,50


def test_regra_5_tetos_de_multa_aluno_e_visitante(client):
    # Aluno: R$ 1,00/dia; teto de R$ 30,00
    u_aluno = client.post("/usuarios", json={"nome": "A Cap", "email": "acap@u.br", "matricula": "MACAP", "categoria": "aluno"}).json()["id"]
    l_id = client.post("/livros", json={"titulo": "L1", "autor": "A1", "isbn": "9781111111111", "ano": 2020, "area_conhecimento": "Geral"}).json()["id"]
    e1 = client.post("/exemplares", json={"livro_id": l_id, "codigo_tombo": "TMB-C1", "estado": "disponivel"}).json()["id"]

    # Retirada 2026-01-01 -> Previsto 2026-01-08 (7 dias). Devolução em 2026-02-17 (40 dias de atraso)
    data_retirada = datetime(2026, 1, 1, 10, 0, 0)
    emp1 = client.post("/emprestimos", json={"usuario_id": u_aluno, "exemplar_id": e1, "data_retirada": data_retirada.isoformat()}).json()["id"]
    data_devolucao = datetime(2026, 2, 17, 10, 0, 0)
    client.post(f"/emprestimos/{emp1}/devolver", json={"data_devolucao": data_devolucao.isoformat()})

    multas_a = client.get(f"/multas/usuario/{u_aluno}").json()
    assert float(multas_a[0]["valor"]) == 30.00  # 40 * 1.00 limitado ao teto 30.00

    # Visitante: R$ 2,00/dia; teto de R$ 20,00
    u_vis = client.post("/usuarios", json={"nome": "V Cap", "email": "vcap@u.br", "matricula": "MVCAP", "categoria": "visitante"}).json()["id"]
    e2 = client.post("/exemplares", json={"livro_id": l_id, "codigo_tombo": "TMB-C2", "estado": "disponivel"}).json()["id"]

    # Retirada 2026-01-01 -> Previsto 2026-01-04 (3 dias). Devolução em 2026-01-19 (15 dias de atraso -> 15 * 2 = 30 > 20)
    emp2 = client.post("/emprestimos", json={"usuario_id": u_vis, "exemplar_id": e2, "data_retirada": data_retirada.isoformat()}).json()["id"]
    data_dev_vis = datetime(2026, 1, 19, 10, 0, 0)
    client.post(f"/emprestimos/{emp2}/devolver", json={"data_devolucao": data_dev_vis.isoformat()})

    multas_v = client.get(f"/multas/usuario/{u_vis}").json()
    assert float(multas_v[0]["valor"]) == 20.00  # limitado ao teto 20.00


def test_pagamento_de_multa_e_desbloqueio(client):
    u_id = client.post("/usuarios", json={"nome": "Pagador", "email": "pag@u.br", "matricula": "MPAG", "categoria": "aluno"}).json()["id"]
    l_id = client.post("/livros", json={"titulo": "L2", "autor": "A2", "isbn": "9782222222222", "ano": 2020, "area_conhecimento": "Geral"}).json()["id"]
    e1 = client.post("/exemplares", json={"livro_id": l_id, "codigo_tombo": "TMB-P1", "estado": "disponivel"}).json()["id"]
    e2 = client.post("/exemplares", json={"livro_id": l_id, "codigo_tombo": "TMB-P2", "estado": "disponivel"}).json()["id"]

    # Empréstimo devolvido com 5 dias de atraso -> gera multa de R$ 5,00
    data_retirada = datetime(2026, 1, 1, 10, 0, 0)
    emp1 = client.post("/emprestimos", json={"usuario_id": u_id, "exemplar_id": e1, "data_retirada": data_retirada.isoformat()}).json()["id"]
    data_devolucao = datetime(2026, 1, 13, 10, 0, 0)
    client.post(f"/emprestimos/{emp1}/devolver", json={"data_devolucao": data_devolucao.isoformat()})

    # Tentar novo empréstimo com multa aberta: deve falhar (Regra 1)
    tentativa = client.post("/emprestimos", json={"usuario_id": u_id, "exemplar_id": e2})
    assert tentativa.status_code == 400
    assert "multa em aberto" in tentativa.json()["detail"]

    # Pagar a multa
    multas = client.get(f"/multas/usuario/{u_id}").json()
    multa_id = multas[0]["id"]
    pag_resp = client.post(f"/multas/{multa_id}/pagar")
    assert pag_resp.status_code == 200
    assert pag_resp.json()["multa"]["estado"] == "paga"

    # Agora novo empréstimo deve ser permitido com sucesso
    sucesso_emp = client.post("/emprestimos", json={"usuario_id": u_id, "exemplar_id": e2})
    assert sucesso_emp.status_code == 201
