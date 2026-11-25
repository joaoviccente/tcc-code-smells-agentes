from datetime import datetime, timedelta


def test_regra_4_fila_reserva_e_devolucao(client):
    # Cria livro e exemplar
    l_resp = client.post(
        "/livros",
        json={"titulo": "Redes de Computadores", "autor": "Kurose", "isbn": "9788522126040", "ano": 2021, "area_conhecimento": "Computação"},
    )
    livro_id = l_resp.json()["id"]

    e_resp = client.post(
        "/exemplares",
        json={"livro_id": livro_id, "codigo_tombo": "TMB-REDES-1", "estado": "disponivel"},
    )
    exemplar_id = e_resp.json()["id"]

    # Cria 3 usuários: Aluno 1 (retira), Aluno 2 (1º na fila), Aluno 3 (2º na fila)
    u1 = client.post("/usuarios", json={"nome": "U1", "email": "u1@u.br", "matricula": "M1", "categoria": "aluno"}).json()["id"]
    u2 = client.post("/usuarios", json={"nome": "U2", "email": "u2@u.br", "matricula": "M2", "categoria": "aluno"}).json()["id"]
    u3 = client.post("/usuarios", json={"nome": "U3", "email": "u3@u.br", "matricula": "M3", "categoria": "aluno"}).json()["id"]

    # U1 pega emprestado
    emp_resp = client.post("/emprestimos", json={"usuario_id": u1, "exemplar_id": exemplar_id})
    assert emp_resp.status_code == 201
    emp_id = emp_resp.json()["id"]

    # U2 reserva
    r2_resp = client.post("/reservas", json={"livro_id": livro_id, "usuario_id": u2})
    assert r2_resp.status_code == 201
    assert r2_resp.json()["posicao_fila"] == 1
    assert r2_resp.json()["estado"] == "aguardando"
    r2_id = r2_resp.json()["id"]

    # U3 reserva
    r3_resp = client.post("/reservas", json={"livro_id": livro_id, "usuario_id": u3})
    assert r3_resp.status_code == 201
    assert r3_resp.json()["posicao_fila"] == 2
    assert r3_resp.json()["estado"] == "aguardando"

    # U1 devolve o exemplar: Regra 4 -> U2 passa ao estado 'disponivel' com 48h
    data_dev = datetime(2026, 11, 15, 12, 0, 0)
    dev_resp = client.post(f"/emprestimos/{emp_id}/devolver", json={"data_devolucao": data_dev.isoformat()})
    assert dev_resp.status_code == 200

    # Verifica exemplar reservado
    ex_resp = client.get(f"/exemplares/{exemplar_id}").json()
    assert ex_resp["estado"] == "reservado"

    # Verifica fila do livro
    fila = client.get(f"/reservas/livro/{livro_id}").json()
    assert len(fila) == 2
    assert fila[0]["usuario_id"] == u2
    assert fila[0]["estado"] == "disponivel"
    assert fila[0]["data_disponibilizacao"] == data_dev.isoformat()

    assert fila[1]["usuario_id"] == u3
    assert fila[1]["estado"] == "aguardando"
    assert fila[1]["posicao_fila"] == 1  # Agora é o primeiro da fila de espera!


def test_regra_4_expiracao_48_horas_passa_vez_ao_proximo(client):
    l_resp = client.post(
        "/livros",
        json={"titulo": "Algoritmos", "autor": "Cormen", "isbn": "9788535236996", "ano": 2012, "area_conhecimento": "Computação"},
    )
    livro_id = l_resp.json()["id"]

    e_resp = client.post(
        "/exemplares",
        json={"livro_id": livro_id, "codigo_tombo": "TMB-ALGO-1", "estado": "disponivel"},
    )
    exemplar_id = e_resp.json()["id"]

    u1 = client.post("/usuarios", json={"nome": "U1", "email": "u1a@u.br", "matricula": "M1a", "categoria": "aluno"}).json()["id"]
    u2 = client.post("/usuarios", json={"nome": "U2", "email": "u2a@u.br", "matricula": "M2a", "categoria": "aluno"}).json()["id"]
    u3 = client.post("/usuarios", json={"nome": "U3", "email": "u3a@u.br", "matricula": "M3a", "categoria": "aluno"}).json()["id"]

    # U1 empresta e reserva para U2 e U3
    emp_id = client.post("/emprestimos", json={"usuario_id": u1, "exemplar_id": exemplar_id}).json()["id"]
    r2_id = client.post("/reservas", json={"livro_id": livro_id, "usuario_id": u2}).json()["id"]
    r3_id = client.post("/reservas", json={"livro_id": livro_id, "usuario_id": u3}).json()["id"]

    # Devolve em 2026-11-10 10:00:00 -> U2 tem até 2026-11-12 10:00:00 (48h)
    dev_time = datetime(2026, 11, 10, 10, 0, 0)
    client.post(f"/emprestimos/{emp_id}/devolver", json={"data_devolucao": dev_time.isoformat()})

    # Consulta com data posterior a 48h (ex: 2026-11-12 11:00:00 -> 49 horas depois)
    # Ao listar a fila, a rotina de expiração roda e passa a vez para U3
    from app.services.reserva_service import processar_expiracoes_reservas
    from app.database import get_db

    db = next(client.app.dependency_overrides[get_db]())
    now_expirado = dev_time + timedelta(hours=49)
    processar_expiracoes_reservas(db, now=now_expirado)

    fila = client.get(f"/reservas/livro/{livro_id}").json()
    assert len(fila) == 1
    assert fila[0]["id"] == r3_id
    assert fila[0]["usuario_id"] == u3
    assert fila[0]["estado"] == "disponivel"


def test_cancelamento_de_reserva(client):
    l_resp = client.post(
        "/livros",
        json={"titulo": "SO", "autor": "Silberschatz", "isbn": "9788521631552", "ano": 2016, "area_conhecimento": "Computação"},
    )
    livro_id = l_resp.json()["id"]
    client.post("/exemplares", json={"livro_id": livro_id, "codigo_tombo": "TMB-SO-1", "estado": "disponivel"})

    u1 = client.post("/usuarios", json={"nome": "U1", "email": "u1b@u.br", "matricula": "M1b", "categoria": "aluno"}).json()["id"]
    r1 = client.post("/reservas", json={"livro_id": livro_id, "usuario_id": u1}).json()

    # Cancelar reserva
    cancel_resp = client.post(f"/reservas/{r1['id']}/cancelar")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["estado"] == "cancelada"

    fila = client.get(f"/reservas/livro/{livro_id}").json()
    assert len(fila) == 0
