from datetime import datetime, timedelta, timezone
from decimal import Decimal


def criar_livro_e_exemplar(client, tombo="TOMBO-M", area="Geral"):
    res_livro = client.post(
        "/livros",
        json={
            "titulo": f"Livro {tombo}",
            "autor": "Autor Teste",
            "isbn": f"ISBN-{tombo}",
            "ano": 2023,
            "area_conhecimento": area,
        },
    )
    livro_id = res_livro.json()["id"]
    res_ex = client.post(
        "/exemplares",
        json={"livro_id": livro_id, "codigo_tombo": tombo, "estado": "disponivel"},
    )
    return livro_id, res_ex.json()["id"]


def test_multa_aluno_diaria_e_teto(client):
    # Aluno: multa R$ 1,00 / dia, teto R$ 30,00
    u = client.post(
        "/usuarios",
        json={"nome": "Aluno Multa", "email": "aluno_m@teste.com", "matricula": "AM01", "categoria": "aluno"},
    ).json()["id"]

    _, ex1 = criar_livro_e_exemplar(client, "ALU-MULTA-1")
    agora = datetime.now(timezone.utc)
    # Prazo de 7 dias. Retirada há 12 dias -> 5 dias de atraso
    retirada = agora - timedelta(days=12)
    emp = client.post(
        "/emprestimos",
        json={"usuario_id": u, "exemplar_id": ex1, "data_retirada": retirada.isoformat()},
    ).json()

    # Devolução hoje -> 5 dias de atraso -> multa = R$ 5,00
    res_dev = client.post(
        f"/emprestimos/{emp['id']}/devolver",
        json={"data_devolucao": agora.isoformat()},
    )
    assert res_dev.status_code == 200

    multas = client.get(f"/multas/usuario/{u}").json()
    assert len(multas) == 1
    assert Decimal(str(multas[0]["valor"])) == Decimal("5.00")
    assert multas[0]["estado"] == "aberta"

    # Agora testar o teto: 40 dias de atraso (sem ultrapassar 60 dias)
    # Prazo aluno: 7 dias. Retirada há 47 dias -> 40 dias de atraso
    _, ex2 = criar_livro_e_exemplar(client, "ALU-MULTA-2")
    # Pagar a primeira multa para poder pegar outro empréstimo
    client.post(f"/multas/{multas[0]['id']}/pagar")

    retirada40 = agora - timedelta(days=47)
    emp2 = client.post(
        "/emprestimos",
        json={"usuario_id": u, "exemplar_id": ex2, "data_retirada": retirada40.isoformat()},
    ).json()

    res_dev2 = client.post(
        f"/emprestimos/{emp2['id']}/devolver",
        json={"data_devolucao": agora.isoformat()},
    )
    assert res_dev2.status_code == 200

    multas_u = client.get(f"/multas/usuario/{u}").json()
    # A última multa deve estar limitada ao teto de R$ 30,00
    multa_aberta = [m for m in multas_u if m["estado"] == "aberta"][0]
    assert Decimal(str(multa_aberta["valor"])) == Decimal("30.00")


def test_multa_professor_perdao_e_teto(client):
    # Professor: multa R$ 0,50 / dia, teto R$ 50,00, perdoada se atraso <= 2 dias
    u = client.post(
        "/usuarios",
        json={"nome": "Prof Multa", "email": "prof_m@teste.com", "matricula": "PM01", "categoria": "professor"},
    ).json()["id"]

    _, ex1 = criar_livro_e_exemplar(client, "PROF-MULTA-1")
    agora = datetime.now(timezone.utc)
    # Prazo de 30 dias. Retirada há 32 dias -> 2 dias de atraso
    retirada2d = agora - timedelta(days=32)
    emp1 = client.post(
        "/emprestimos",
        json={"usuario_id": u, "exemplar_id": ex1, "data_retirada": retirada2d.isoformat()},
    ).json()

    # Devolver com 2 dias de atraso: deve ser PERDOADA automaticamente
    res_dev1 = client.post(
        f"/emprestimos/{emp1['id']}/devolver",
        json={"data_devolucao": agora.isoformat()},
    )
    assert res_dev1.status_code == 200

    multas1 = client.get(f"/multas/usuario/{u}").json()
    assert len(multas1) == 1
    assert multas1[0]["estado"] == "perdoada"
    assert Decimal(str(multas1[0]["valor"])) == Decimal("1.00")  # 2 * 0.50

    # Com 3 dias de atraso (33 dias desde retirada): NÃO é perdoada
    _, ex2 = criar_livro_e_exemplar(client, "PROF-MULTA-2")
    retirada3d = agora - timedelta(days=33)
    emp2 = client.post(
        "/emprestimos",
        json={"usuario_id": u, "exemplar_id": ex2, "data_retirada": retirada3d.isoformat()},
    ).json()

    res_dev2 = client.post(
        f"/emprestimos/{emp2['id']}/devolver",
        json={"data_devolucao": agora.isoformat()},
    )
    assert res_dev2.status_code == 200

    multas2 = client.get(f"/multas/usuario/{u}").json()
    multa_aberta = [m for m in multas2 if m["estado"] == "aberta"][0]
    assert Decimal(str(multa_aberta["valor"])) == Decimal("1.50")  # 3 * 0.50


def test_multa_visitante(client):
    # Visitante: multa R$ 2,00 / dia, teto R$ 20,00
    u = client.post(
        "/usuarios",
        json={"nome": "Vis Multa", "email": "vis_m@teste.com", "matricula": "VM01", "categoria": "visitante"},
    ).json()["id"]

    _, ex1 = criar_livro_e_exemplar(client, "VIS-MULTA-1")
    agora = datetime.now(timezone.utc)
    # Prazo visitante: 3 dias. Retirada há 7 dias -> 4 dias de atraso
    retirada = agora - timedelta(days=7)
    emp = client.post(
        "/emprestimos",
        json={"usuario_id": u, "exemplar_id": ex1, "data_retirada": retirada.isoformat()},
    ).json()

    # Devolver com 4 dias de atraso: 4 * 2.00 = 8.00
    res_dev = client.post(
        f"/emprestimos/{emp['id']}/devolver",
        json={"data_devolucao": agora.isoformat()},
    )
    assert res_dev.status_code == 200
    multas = client.get(f"/multas/usuario/{u}").json()
    assert Decimal(str(multas[0]["valor"])) == Decimal("8.00")

    # Pagar a multa
    multa_id = multas[0]["id"]
    res_pag = client.post(f"/multas/{multa_id}/pagar")
    assert res_pag.status_code == 200
    assert res_pag.json()["multa"]["estado"] == "paga"

    # Tentar pagar novamente
    res_pag_rep = client.post(f"/multas/{multa_id}/pagar")
    assert res_pag_rep.status_code == 400


def test_regra_2_suspensao_por_atraso_maior_que_15_dias(client):
    # Usuário com atraso > 15 dias é suspenso por dobro dos dias
    u = client.post(
        "/usuarios",
        json={"nome": "Atrasado", "email": "atrasado@teste.com", "matricula": "ATR01", "categoria": "aluno"},
    ).json()["id"]

    _, ex = criar_livro_e_exemplar(client, "SUSP-1")
    agora = datetime.now(timezone.utc)
    # Prazo aluno: 7 dias. Retirada há 27 dias -> 20 dias de atraso (> 15)
    retirada = agora - timedelta(days=27)

    emp = client.post(
        "/emprestimos",
        json={"usuario_id": u, "exemplar_id": ex, "data_retirada": retirada.isoformat()},
    ).json()

    # Devolução hoje -> 20 dias de atraso -> suspensão de 40 dias
    res_dev = client.post(
        f"/emprestimos/{emp['id']}/devolver",
        json={"data_devolucao": agora.isoformat()},
    )
    assert res_dev.status_code == 200

    # Verificar situação do usuário
    user_info = client.get(f"/usuarios/{u}").json()
    assert user_info["situacao"] == "suspenso"
    assert user_info["data_fim_suspensao"] is not None

    fim_suspensao = datetime.fromisoformat(user_info["data_fim_suspensao"])
    dias_suspensao = (fim_suspensao.date() - agora.date()).days
    assert dias_suspensao == 40  # 2 * 20 dias

    # Usuário suspenso tenta novo empréstimo -> Negado (Regra 1)
    _, ex2 = criar_livro_e_exemplar(client, "SUSP-2")
    res_emp = client.post("/emprestimos", json={"usuario_id": u, "exemplar_id": ex2})
    assert res_emp.status_code == 400
    assert "suspenso" in res_emp.json()["detail"].lower()


def test_regra_7_atraso_maior_que_60_dias_baixa_exemplar_e_teto(client):
    # Devolução de exemplar com mais de 60 dias de atraso marca exemplar como baixado e gera multa no teto
    u = client.post(
        "/usuarios",
        json={"nome": "Perdido", "email": "perdido@teste.com", "matricula": "PRD01", "categoria": "aluno"},
    ).json()["id"]

    _, ex = criar_livro_e_exemplar(client, "BX-60")
    agora = datetime.now(timezone.utc)
    # Prazo aluno: 7 dias. Retirada há 70 dias -> 63 dias de atraso (> 60)
    retirada = agora - timedelta(days=70)

    emp = client.post(
        "/emprestimos",
        json={"usuario_id": u, "exemplar_id": ex, "data_retirada": retirada.isoformat()},
    ).json()

    res_dev = client.post(
        f"/emprestimos/{emp['id']}/devolver",
        json={"data_devolucao": agora.isoformat()},
    )
    assert res_dev.status_code == 200

    # Exemplar deve estar BAIXADO
    ex_info = client.get(f"/exemplares/{ex}").json()
    assert ex_info["estado"] == "baixado"

    # Multa deve ser no valor do teto do aluno (R$ 30,00)
    multas = client.get(f"/multas/usuario/{u}").json()
    assert len(multas) == 1
    assert Decimal(str(multas[0]["valor"])) == Decimal("30.00")
    assert multas[0]["estado"] == "aberta"

    # Usuário também foi suspenso por 2 * 63 = 126 dias
    user_info = client.get(f"/usuarios/{u}").json()
    assert user_info["situacao"] == "suspenso"
    fim_susp = datetime.fromisoformat(user_info["data_fim_suspensao"])
    assert (fim_susp.date() - agora.date()).days == 126
