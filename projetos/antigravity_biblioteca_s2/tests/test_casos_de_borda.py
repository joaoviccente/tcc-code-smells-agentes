from datetime import datetime, timedelta, timezone
from decimal import Decimal


def criar_livro_e_exemplar(client, tombo="TB-EDGE", estado="disponivel"):
    res_livro = client.post(
        "/livros",
        json={
            "titulo": f"Livro {tombo}",
            "autor": "Autor Borda",
            "isbn": f"ISBN-{tombo}",
            "ano": 2024,
            "area_conhecimento": "Filosofia",
        },
    )
    livro_id = res_livro.json()["id"]
    res_ex = client.post(
        "/exemplares",
        json={"livro_id": livro_id, "codigo_tombo": tombo, "estado": estado},
    )
    return livro_id, res_ex.json()["id"]


def test_bloqueio_por_multa_aberta_e_desbloqueio_apos_pagamento(client):
    # Criar usuário aluno
    u = client.post(
        "/usuarios",
        json={"nome": "Aluno Multado", "email": "multado@teste.com", "matricula": "M001", "categoria": "aluno"},
    ).json()["id"]

    _, ex1 = criar_livro_e_exemplar(client, "M-EX1")
    _, ex2 = criar_livro_e_exemplar(client, "M-EX2")

    agora = datetime.now(timezone.utc)
    # Empréstimo devolvido com 3 dias de atraso
    retirada = agora - timedelta(days=10)
    emp1 = client.post(
        "/emprestimos",
        json={"usuario_id": u, "exemplar_id": ex1, "data_retirada": retirada.isoformat()},
    ).json()

    # Devolve hoje -> gera multa aberta de R$ 3,00
    res_dev = client.post(
        f"/emprestimos/{emp1['id']}/devolver",
        json={"data_devolucao": agora.isoformat()},
    )
    assert res_dev.status_code == 200

    # Tenta pegar novo exemplar -> Bloqueado pela Regra 1 (multa aberta)
    res_emp2 = client.post("/emprestimos", json={"usuario_id": u, "exemplar_id": ex2})
    assert res_emp2.status_code == 400
    assert "multa aberta" in res_emp2.json()["detail"].lower()

    # Pagar a multa
    multas = client.get(f"/multas/usuario/{u}").json()
    assert len(multas) == 1
    multa_id = multas[0]["id"]

    res_pag = client.post(f"/multas/{multa_id}/pagar")
    assert res_pag.status_code == 200

    # Agora o empréstimo deve ser aceito!
    res_emp2_pos = client.post("/emprestimos", json={"usuario_id": u, "exemplar_id": ex2})
    assert res_emp2_pos.status_code == 201


def test_restauracao_apos_fim_da_suspensao(client):
    u = client.post(
        "/usuarios",
        json={"nome": "Aluno Suspenso", "email": "susp_fim@teste.com", "matricula": "S001", "categoria": "aluno"},
    ).json()["id"]

    _, ex1 = criar_livro_e_exemplar(client, "SF-EX1")
    agora = datetime.now(timezone.utc)
    # Atraso de 16 dias (> 15) -> suspensão de 32 dias
    retirada = agora - timedelta(days=23)  # 7 + 16
    emp = client.post(
        "/emprestimos",
        json={"usuario_id": u, "exemplar_id": ex1, "data_retirada": retirada.isoformat()},
    ).json()

    client.post(
        f"/emprestimos/{emp['id']}/devolver",
        json={"data_devolucao": agora.isoformat()},
    )

    # Verificar que está suspenso
    user = client.get(f"/usuarios/{u}").json()
    assert user["situacao"] == "suspenso"

    # Se consultar o usuário 33 dias no futuro (após o fim da suspensão)
    futuro_33d = agora + timedelta(days=33)
    user_futuro = client.get(f"/usuarios/{u}", params={"data_referencia": futuro_33d.isoformat()}).json()
    assert user_futuro["situacao"] == "ativo"


def test_tentar_reservar_livro_sem_exemplares_validos(client):
    res_l = client.post(
        "/livros",
        json={"titulo": "Livro Danificado", "autor": "Autor", "isbn": "ISBN-DANIF", "ano": 2020, "area_conhecimento": "Artes"},
    ).json()["id"]

    # Criar apenas exemplares baixados ou em reparo
    client.post("/exemplares", json={"livro_id": res_l, "codigo_tombo": "DAN-1", "estado": "em_reparo"})
    client.post("/exemplares", json={"livro_id": res_l, "codigo_tombo": "DAN-2", "estado": "baixado"})

    u = client.post(
        "/usuarios",
        json={"nome": "Reserva Falha", "email": "rf@teste.com", "matricula": "RF01", "categoria": "aluno"},
    ).json()["id"]

    res = client.post("/reservas", json={"livro_id": res_l, "usuario_id": u})
    assert res.status_code == 400
    assert "em reparo ou baixados" in res.json()["detail"].lower()


def test_operacoes_duplicadas_e_invalidas(client):
    _, ex = criar_livro_e_exemplar(client, "INV-OP")
    u = client.post(
        "/usuarios",
        json={"nome": "Operacoes", "email": "op@teste.com", "matricula": "OP01", "categoria": "aluno"},
    ).json()["id"]

    emp = client.post("/emprestimos", json={"usuario_id": u, "exemplar_id": ex}).json()
    emp_id = emp["id"]

    # Devolve empréstimo
    client.post(f"/emprestimos/{emp_id}/devolver")

    # Tenta devolver novamente
    res_dev2 = client.post(f"/emprestimos/{emp_id}/devolver")
    assert res_dev2.status_code == 400

    # Tenta renovar empréstimo já devolvido
    res_renov = client.post(f"/emprestimos/{emp_id}/renovar")
    assert res_renov.status_code == 400


def test_rotas_status_e_health(client):
    r_root = client.get("/")
    assert r_root.status_code == 200
    assert r_root.json()["status"] == "online"

    r_health = client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "healthy"
