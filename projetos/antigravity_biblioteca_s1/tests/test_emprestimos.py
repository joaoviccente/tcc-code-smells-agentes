from datetime import datetime

def test_prazos_e_limites_emprestimo(client):
    # Criar Livro
    res_l = client.post("/livros", json={
        "titulo": "Banco de Dados",
        "autor": "Silberschatz",
        "isbn": "978-85-8260-156-3",
        "ano": 2016,
        "area_conhecimento": "Computação"
    })
    livro_id = res_l.json()["id"]

    # Criar 10 exemplares
    exemplares = []
    for i in range(1, 11):
        res_e = client.post("/exemplares", json={
            "livro_id": livro_id,
            "codigo_tombo": f"T-BANCO-{i}",
            "estado": "disponivel"
        })
        exemplares.append(res_e.json()["id"])

    # Criar Aluno, Professor, Visitante
    u_aluno = client.post("/usuarios", json={
        "nome": "Aluno 1", "email": "a1@test.com", "matricula": "A001", "categoria": "aluno"
    }).json()["id"]

    u_prof = client.post("/usuarios", json={
        "nome": "Prof 1", "email": "p1@test.com", "matricula": "P001", "categoria": "professor"
    }).json()["id"]

    u_vis = client.post("/usuarios", json={
        "nome": "Vis 1", "email": "v1@test.com", "matricula": "V001", "categoria": "visitante"
    }).json()["id"]

    # 1. Aluno: prazo 7 dias
    emp_a = client.post("/emprestimos", json={
        "usuario_id": u_aluno,
        "exemplar_id": exemplares[0],
        "data_retirada": "2026-11-01T10:00:00"
    }).json()
    dt_ret = datetime.fromisoformat(emp_a["data_retirada"])
    dt_prev = datetime.fromisoformat(emp_a["data_prevista"])
    assert (dt_prev.date() - dt_ret.date()).days == 7

    # 2. Professor: prazo 30 dias
    emp_p = client.post("/emprestimos", json={
        "usuario_id": u_prof,
        "exemplar_id": exemplares[1],
        "data_retirada": "2026-11-01T10:00:00"
    }).json()
    dt_ret = datetime.fromisoformat(emp_p["data_retirada"])
    dt_prev = datetime.fromisoformat(emp_p["data_prevista"])
    assert (dt_prev.date() - dt_ret.date()).days == 30

    # 3. Visitante: prazo 3 dias
    emp_v = client.post("/emprestimos", json={
        "usuario_id": u_vis,
        "exemplar_id": exemplares[2],
        "data_retirada": "2026-11-01T10:00:00"
    }).json()
    dt_ret = datetime.fromisoformat(emp_v["data_retirada"])
    dt_prev = datetime.fromisoformat(emp_v["data_prevista"])
    assert (dt_prev.date() - dt_ret.date()).days == 3

    # Testar Limite Visitante (limite = 1)
    # Já tem 1 exemplar (exemplares[2]), tentar pegar outro
    res_limite_vis = client.post("/emprestimos", json={
        "usuario_id": u_vis,
        "exemplar_id": exemplares[3]
    })
    assert res_limite_vis.status_code == 400
    assert "limite de 1 exemplares atingido" in res_limite_vis.json()["detail"]

    # Testar Limite Aluno (limite = 3)
    # Já tem 1 (exemplares[0]). Pegar 2 e 3.
    res_a2 = client.post("/emprestimos", json={"usuario_id": u_aluno, "exemplar_id": exemplares[3]})
    assert res_a2.status_code == 201
    res_a3 = client.post("/emprestimos", json={"usuario_id": u_aluno, "exemplar_id": exemplares[4]})
    assert res_a3.status_code == 201

    # Tentar o 4º exemplar
    res_a4 = client.post("/emprestimos", json={"usuario_id": u_aluno, "exemplar_id": exemplares[5]})
    assert res_a4.status_code == 400
    assert "limite de 3 exemplares atingido" in res_a4.json()["detail"]

    # Devolver exemplar do aluno libera espaço
    res_dev = client.post(f"/emprestimos/{emp_a['id']}/devolver", json={
        "data_devolucao": "2026-11-05T10:00:00"
    })
    assert res_dev.status_code == 200
    assert res_dev.json()["estado"] == "devolvido"

    # Agora o aluno pode pegar novamente
    res_a_novo = client.post("/emprestimos", json={"usuario_id": u_aluno, "exemplar_id": exemplares[5]})
    assert res_a_novo.status_code == 201
