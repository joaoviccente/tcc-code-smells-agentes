from datetime import datetime, timedelta, timezone


def test_regra_2_suspensao_automatica_por_atraso_superior_15_dias(client):
    # Cria usuário Aluno
    u_resp = client.post(
        "/usuarios",
        json={"nome": "Atrasado Cronico", "email": "atraso@uni.br", "matricula": "M-ATRASO", "categoria": "aluno"},
    )
    u_id = u_resp.json()["id"]

    # Cria livro e 2 exemplares
    l_resp = client.post(
        "/livros",
        json={"titulo": "Livro Atraso", "autor": "Autor", "isbn": "9781231231231", "ano": 2020, "area_conhecimento": "Direito"},
    )
    l_id = l_resp.json()["id"]

    e1 = client.post("/exemplares", json={"livro_id": l_id, "codigo_tombo": "TMB-ATR-1", "estado": "disponivel"}).json()["id"]
    e2 = client.post("/exemplares", json={"livro_id": l_id, "codigo_tombo": "TMB-ATR-2", "estado": "disponivel"}).json()["id"]

    # Retirada há 25 dias (prazo aluno é 7 dias -> atraso atual = 18 dias (> 15 dias!))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    data_retirada = now - timedelta(days=25)
    client.post("/emprestimos", json={"usuario_id": u_id, "exemplar_id": e1, "data_retirada": data_retirada.isoformat()})

    # Consulta do usuário: a Regra 2 deve detectar o atraso > 15 dias e suspendê-lo automaticamente
    u_check = client.get(f"/usuarios/{u_id}").json()
    assert u_check["situacao"] == "suspenso"
    assert u_check["suspenso_ate"] is not None

    # Tenta realizar novo empréstimo enquanto suspenso: deve falhar (Regra 1)
    tentativa = client.post("/emprestimos", json={"usuario_id": u_id, "exemplar_id": e2})
    assert tentativa.status_code == 400
    assert "usuário está suspenso" in tentativa.json()["detail"]


def test_retirada_de_exemplar_reservado_conclui_reserva(client):
    # Cria livro e exemplar
    l_resp = client.post(
        "/livros",
        json={"titulo": "Engenharia de Software", "autor": "Pressman", "isbn": "9788580555332", "ano": 2016, "area_conhecimento": "Computação"},
    )
    l_id = l_resp.json()["id"]
    e_id = client.post("/exemplares", json={"livro_id": l_id, "codigo_tombo": "TMB-ENG-1", "estado": "disponivel"}).json()["id"]

    u1 = client.post("/usuarios", json={"nome": "U1", "email": "u1eng@u.br", "matricula": "M1eng", "categoria": "aluno"}).json()["id"]
    u2 = client.post("/usuarios", json={"nome": "U2", "email": "u2eng@u.br", "matricula": "M2eng", "categoria": "aluno"}).json()["id"]

    # U1 pega emprestado
    emp1 = client.post("/emprestimos", json={"usuario_id": u1, "exemplar_id": e_id}).json()["id"]

    # U2 reserva
    res_u2 = client.post("/reservas", json={"livro_id": l_id, "usuario_id": u2}).json()
    assert res_u2["posicao_fila"] == 1

    # U1 devolve -> exemplar fica 'reservado' e reserva de U2 fica 'disponivel'
    client.post(f"/emprestimos/{emp1}/devolver")

    ex_check = client.get(f"/exemplares/{e_id}").json()
    assert ex_check["estado"] == "reservado"

    # Terceiro usuário U3 tenta pegar o exemplar reservado para U2 -> Deve falhar!
    u3 = client.post("/usuarios", json={"nome": "U3", "email": "u3eng@u.br", "matricula": "M3eng", "categoria": "aluno"}).json()["id"]
    resp_u3 = client.post("/emprestimos", json={"usuario_id": u3, "exemplar_id": e_id})
    assert resp_u3.status_code == 400
    assert "reservado para outro usuário" in resp_u3.json()["detail"]

    # U2 (titular da reserva) retira o exemplar -> Sucesso!
    resp_u2 = client.post("/emprestimos", json={"usuario_id": u2, "exemplar_id": e_id})
    assert resp_u2.status_code == 201
    assert resp_u2.json()["estado"] == "ativo"

    # Verifica que a fila de reserva para este livro está vazia agora
    fila = client.get(f"/reservas/livro/{l_id}").json()
    assert len(fila) == 0


def test_professor_limite_8_exemplares_e_4_renovacoes(client):
    # Professor tem limite de 8 exemplares e 4 renovações
    u_prof = client.post("/usuarios", json={"nome": "Prof Top", "email": "proftop@u.br", "matricula": "MPTOP", "categoria": "professor"}).json()["id"]
    l_id = client.post("/livros", json={"titulo": "Livro Prof", "autor": "Autor", "isbn": "9783333333333", "ano": 2021, "area_conhecimento": "Educação"}).json()["id"]

    exemplares = []
    for i in range(8):
        eid = client.post("/exemplares", json={"livro_id": l_id, "codigo_tombo": f"TMB-PROF-{i+1}", "estado": "disponivel"}).json()["id"]
        exemplares.append(eid)

    # Realiza 8 empréstimos
    emprestimos = []
    for eid in exemplares:
        emp = client.post("/emprestimos", json={"usuario_id": u_prof, "exemplar_id": eid})
        assert emp.status_code == 201
        emprestimos.append(emp.json()["id"])

    # 9º exemplar deve falhar (limite de 8 exemplares)
    e9 = client.post("/exemplares", json={"livro_id": l_id, "codigo_tombo": "TMB-PROF-9", "estado": "disponivel"}).json()["id"]
    emp9 = client.post("/emprestimos", json={"usuario_id": u_prof, "exemplar_id": e9})
    assert emp9.status_code == 400
    assert "limite de 8 exemplar(es) atingido" in emp9.json()["detail"]

    # Testa 4 renovações no 1º empréstimo
    emp_test = emprestimos[0]
    for r in range(1, 5):
        renov = client.post(f"/emprestimos/{emp_test}/renovar")
        assert renov.status_code == 200
        assert renov.json()["numero_renovacoes"] == r

    # 5ª renovação deve falhar
    renov5 = client.post(f"/emprestimos/{emp_test}/renovar")
    assert renov5.status_code == 400
    assert "limite de 4 renovação(ões) atingido" in renov5.json()["detail"]
