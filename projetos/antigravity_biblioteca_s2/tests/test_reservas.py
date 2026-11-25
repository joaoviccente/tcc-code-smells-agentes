from datetime import datetime, timedelta, timezone


def criar_livro_e_exemplar(client, tombo="TOMBO-RES", estado="disponivel"):
    res_livro = client.post(
        "/livros",
        json={
            "titulo": f"Livro {tombo}",
            "autor": "Autor Teste",
            "isbn": f"ISBN-{tombo}",
            "ano": 2024,
            "area_conhecimento": "Engenharia",
        },
    )
    livro_id = res_livro.json()["id"]
    res_ex = client.post(
        "/exemplares",
        json={"livro_id": livro_id, "codigo_tombo": tombo, "estado": estado},
    )
    return livro_id, res_ex.json()["id"]


def test_fila_de_reservas_e_devolucao_48h(client):
    # Criar livro com 1 exemplar
    livro_id, ex_id = criar_livro_e_exemplar(client, "FILA-1")

    # Criar 3 usuários
    u1 = client.post(
        "/usuarios",
        json={"nome": "U1", "email": "u1_f@teste.com", "matricula": "UF01", "categoria": "aluno"},
    ).json()["id"]
    u2 = client.post(
        "/usuarios",
        json={"nome": "U2", "email": "u2_f@teste.com", "matricula": "UF02", "categoria": "aluno"},
    ).json()["id"]
    u3 = client.post(
        "/usuarios",
        json={"nome": "U3", "email": "u3_f@teste.com", "matricula": "UF03", "categoria": "aluno"},
    ).json()["id"]

    # U1 pega o livro
    emp = client.post("/emprestimos", json={"usuario_id": u1, "exemplar_id": ex_id}).json()

    # U2 reserva o livro -> entra como posicao 1 na fila (aguardando)
    res_r2 = client.post("/reservas", json={"livro_id": livro_id, "usuario_id": u2}).json()
    assert res_r2["posicao_fila"] == 1
    assert res_r2["estado"] == "aguardando"

    # U3 reserva o livro -> entra como posicao 2 na fila (aguardando)
    res_r3 = client.post("/reservas", json={"livro_id": livro_id, "usuario_id": u3}).json()
    assert res_r3["posicao_fila"] == 2
    assert res_r3["estado"] == "aguardando"

    # U1 devolve o exemplar: primeiro da fila (U2) passa a DISPONIVEL e tem 48h para retirar
    agora = datetime.now(timezone.utc)
    res_dev = client.post(
        f"/emprestimos/{emp['id']}/devolver",
        json={"data_devolucao": agora.isoformat()},
    )
    assert res_dev.status_code == 200

    # Exemplar passa ao estado RESERVADO
    ex_info = client.get(f"/exemplares/{ex_id}").json()
    assert ex_info["estado"] == "reservado"

    # Verificar fila do livro
    fila = client.get(f"/reservas/livro/{livro_id}").json()
    assert len(fila) == 2
    # U2 é o primeiro e está disponível
    assert fila[0]["usuario_id"] == u2
    assert fila[0]["estado"] == "disponivel"
    assert fila[0]["data_limite_retirada"] is not None
    # U3 continua aguardando
    assert fila[1]["usuario_id"] == u3
    assert fila[1]["estado"] == "aguardando"

    # Outro usuário (U1 ou U3) tenta pegar o exemplar reservado para U2 -> NEGADO
    res_emp_invalido = client.post("/emprestimos", json={"usuario_id": u3, "exemplar_id": ex_id})
    assert res_emp_invalido.status_code == 400
    assert "reservado" in res_emp_invalido.json()["detail"].lower()

    # Simular que se passaram 49 horas (> 48h): reserva de U2 expira e passa para U3
    depois_49h = agora + timedelta(hours=49)
    res_exp = client.post(
        "/reservas/processar-expiracoes",
        params={"data_referencia": depois_49h.isoformat()},
    )
    assert res_exp.status_code == 200

    # Agora U3 está como DISPONIVEL
    fila_atualizada = client.get(f"/reservas/livro/{livro_id}").json()
    assert len(fila_atualizada) == 1
    assert fila_atualizada[0]["usuario_id"] == u3
    assert fila_atualizada[0]["estado"] == "disponivel"

    # Agora U3 retira o exemplar com sucesso!
    res_emp_u3 = client.post("/emprestimos", json={"usuario_id": u3, "exemplar_id": ex_id})
    assert res_emp_u3.status_code == 201

    # Exemplar agora está emprestado
    assert client.get(f"/exemplares/{ex_id}").json()["estado"] == "emprestado"


def test_regra_6_cancelamento_reservas_se_ultimo_exemplar_baixado(client):
    # Se o último exemplar disponível for baixado, todas as reservas daquele livro são canceladas
    livro_id, ex_id = criar_livro_e_exemplar(client, "ULTIMO-BX")

    u1 = client.post(
        "/usuarios",
        json={"nome": "UR1", "email": "ur1@teste.com", "matricula": "UR01", "categoria": "aluno"},
    ).json()["id"]
    u2 = client.post(
        "/usuarios",
        json={"nome": "UR2", "email": "ur2@teste.com", "matricula": "UR02", "categoria": "aluno"},
    ).json()["id"]

    # Fazer 2 reservas
    r1 = client.post("/reservas", json={"livro_id": livro_id, "usuario_id": u1}).json()
    r2 = client.post("/reservas", json={"livro_id": livro_id, "usuario_id": u2}).json()

    # Atualizar o único exemplar do livro para BAIXADO
    res_put = client.put(f"/exemplares/{ex_id}", json={"estado": "baixado"})
    assert res_put.status_code == 200

    # Todas as reservas daquele livro devem ter sido canceladas
    res_r1 = client.get(f"/reservas/{r1['id']}").json()
    res_r2 = client.get(f"/reservas/{r2['id']}").json()
    assert res_r1["estado"] == "cancelada"
    assert res_r2["estado"] == "cancelada"


def test_cancelar_reserva_voluntariamente(client):
    livro_id, ex_id = criar_livro_e_exemplar(client, "CANC-VOL")
    u1 = client.post(
        "/usuarios",
        json={"nome": "Canc1", "email": "canc1@teste.com", "matricula": "C01", "categoria": "aluno"},
    ).json()["id"]

    r = client.post("/reservas", json={"livro_id": livro_id, "usuario_id": u1}).json()
    res_canc = client.post(f"/reservas/{r['id']}/cancelar")
    assert res_canc.status_code == 200
    assert res_canc.json()["estado"] == "cancelada"
