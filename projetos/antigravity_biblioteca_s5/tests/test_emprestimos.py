from datetime import datetime, timedelta, timezone


def criar_cenario_base(client, categoria="aluno"):
    u_resp = client.post(
        "/usuarios",
        json={"nome": f"User {categoria}", "email": f"{categoria}@u.br", "matricula": f"M_{categoria}", "categoria": categoria},
    )
    usuario_id = u_resp.json()["id"]

    l_resp = client.post(
        "/livros",
        json={"titulo": "Livro Teste", "autor": "Autor", "isbn": f"978{usuario_id}00000000"[:13], "ano": 2020, "area_conhecimento": "Computação"},
    )
    livro_id = l_resp.json()["id"]

    e_resp = client.post(
        "/exemplares",
        json={"livro_id": livro_id, "codigo_tombo": f"TMB-{usuario_id}-1", "estado": "disponivel"},
    )
    exemplar_id = e_resp.json()["id"]

    return usuario_id, livro_id, exemplar_id


def test_prazos_por_categoria(client):
    # Aluno: 7 dias
    u_aluno, _, e_aluno = criar_cenario_base(client, "aluno")
    now = datetime(2026, 11, 10, 10, 0, 0)
    emp1 = client.post("/emprestimos", json={"usuario_id": u_aluno, "exemplar_id": e_aluno, "data_retirada": now.isoformat()}).json()
    assert (datetime.fromisoformat(emp1["data_prevista"]) - now).days == 7

    # Professor: 30 dias
    u_prof, _, e_prof = criar_cenario_base(client, "professor")
    emp2 = client.post("/emprestimos", json={"usuario_id": u_prof, "exemplar_id": e_prof, "data_retirada": now.isoformat()}).json()
    assert (datetime.fromisoformat(emp2["data_prevista"]) - now).days == 30

    # Visitante: 3 dias
    u_vis, _, e_vis = criar_cenario_base(client, "visitante")
    emp3 = client.post("/emprestimos", json={"usuario_id": u_vis, "exemplar_id": e_vis, "data_retirada": now.isoformat()}).json()
    assert (datetime.fromisoformat(emp3["data_prevista"]) - now).days == 3


def test_limite_exemplares_por_categoria(client):
    # Visitante tem limite de 1 exemplar
    u_vis, l_id, e_vis1 = criar_cenario_base(client, "visitante")
    e_vis2 = client.post("/exemplares", json={"livro_id": l_id, "codigo_tombo": "TMB-VIS-2", "estado": "disponivel"}).json()["id"]

    # 1º empréstimo: sucesso
    resp1 = client.post("/emprestimos", json={"usuario_id": u_vis, "exemplar_id": e_vis1})
    assert resp1.status_code == 201

    # 2º empréstimo: deve falhar (Regra 1 e limite da categoria)
    resp2 = client.post("/emprestimos", json={"usuario_id": u_vis, "exemplar_id": e_vis2})
    assert resp2.status_code == 400
    assert "limite de 1 exemplar(es) atingido" in resp2.json()["detail"]


def test_renovacoes_por_categoria_e_limite(client):
    # Visitante: 0 renovações
    u_vis, _, e_vis = criar_cenario_base(client, "visitante")
    emp_vis = client.post("/emprestimos", json={"usuario_id": u_vis, "exemplar_id": e_vis}).json()["id"]
    renov_vis = client.post(f"/emprestimos/{emp_vis}/renovar")
    assert renov_vis.status_code == 400
    assert "limite de 0 renovação(ões) atingido" in renov_vis.json()["detail"]

    # Aluno: 2 renovações permitidas, 3ª rejeitada
    u_aluno, _, e_aluno = criar_cenario_base(client, "aluno")
    now = datetime(2026, 11, 10, 10, 0, 0)
    emp_aluno = client.post("/emprestimos", json={"usuario_id": u_aluno, "exemplar_id": e_aluno, "data_retirada": now.isoformat()}).json()["id"]

    # 1ª renovação
    r1 = client.post(f"/emprestimos/{emp_aluno}/renovar")
    assert r1.status_code == 200
    assert r1.json()["numero_renovacoes"] == 1

    # 2ª renovação
    r2 = client.post(f"/emprestimos/{emp_aluno}/renovar")
    assert r2.status_code == 200
    assert r2.json()["numero_renovacoes"] == 2

    # 3ª renovação deve falhar
    r3 = client.post(f"/emprestimos/{emp_aluno}/renovar")
    assert r3.status_code == 400
    assert "limite de 2 renovação(ões) atingido" in r3.json()["detail"]


def test_regra_3_renovacao_negada_com_fila_de_reserva(client):
    u_aluno, l_id, e_aluno = criar_cenario_base(client, "aluno")
    emp_id = client.post("/emprestimos", json={"usuario_id": u_aluno, "exemplar_id": e_aluno}).json()["id"]

    # Outro aluno reserva o mesmo livro
    u_outro = client.post("/usuarios", json={"nome": "Outro", "email": "outro@u.br", "matricula": "M-OUTRO", "categoria": "aluno"}).json()["id"]
    client.post("/reservas", json={"livro_id": l_id, "usuario_id": u_outro})

    # Tenta renovar o empréstimo: deve ser negado pela fila de reserva
    renov = client.post(f"/emprestimos/{emp_id}/renovar")
    assert renov.status_code == 400
    assert "há reservas na fila para este livro" in renov.json()["detail"]


def test_regra_6_exemplar_em_reparo_ou_baixado_nao_pode_ser_emprestado(client):
    u_aluno, l_id, _ = criar_cenario_base(client, "aluno")

    e_reparo = client.post("/exemplares", json={"livro_id": l_id, "codigo_tombo": "TMB-REP", "estado": "em_reparo"}).json()["id"]
    e_baixado = client.post("/exemplares", json={"livro_id": l_id, "codigo_tombo": "TMB-BAIX", "estado": "baixado"}).json()["id"]

    resp1 = client.post("/emprestimos", json={"usuario_id": u_aluno, "exemplar_id": e_reparo})
    assert resp1.status_code == 400
    assert "em reparo" in resp1.json()["detail"]

    resp2 = client.post("/emprestimos", json={"usuario_id": u_aluno, "exemplar_id": e_baixado})
    assert resp2.status_code == 400
    assert "baixado" in resp2.json()["detail"]


def test_regra_7_devolucao_com_mais_de_60_dias_de_atraso(client):
    # Aluno: prazo 7 dias. Retirada há 78 dias -> 71 dias de atraso (> 60 dias).
    u_aluno, _, e_id = criar_cenario_base(client, "aluno")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    data_retirada = now - timedelta(days=78)
    emp_id = client.post("/emprestimos", json={"usuario_id": u_aluno, "exemplar_id": e_id, "data_retirada": data_retirada.isoformat()}).json()["id"]

    data_devolucao = now
    dev_resp = client.post(f"/emprestimos/{emp_id}/devolver", json={"data_devolucao": data_devolucao.isoformat()})
    assert dev_resp.status_code == 200

    # Exemplar deve estar baixado (Regra 7)
    exemplar_resp = client.get(f"/exemplares/{e_id}").json()
    assert exemplar_resp["estado"] == "baixado"

    # Multa deve ser gerada no valor do teto da categoria Aluno (R$ 30,00)
    multas = client.get(f"/multas/usuario/{u_aluno}").json()
    assert len(multas) == 1
    assert float(multas[0]["valor"]) == 30.00
    assert multas[0]["estado"] == "aberta"

    # Usuário deve estar suspenso pelo dobro dos dias de atraso (Regra 2)
    # Atraso de 71 dias -> suspensão de 142 dias a partir da data de devolução
    usuario_resp = client.get(f"/usuarios/{u_aluno}").json()
    assert usuario_resp["situacao"] == "suspenso"
    assert usuario_resp["suspenso_ate"] is not None
    dias_susp = (datetime.fromisoformat(usuario_resp["suspenso_ate"]) - data_devolucao).days
    assert dias_susp == 2 * 71
