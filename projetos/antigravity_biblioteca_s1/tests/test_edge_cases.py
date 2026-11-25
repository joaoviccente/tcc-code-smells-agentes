from datetime import datetime, timedelta

def test_deletar_entidades_com_emprestimos_e_sem_emprestimos(client):
    # Setup: Livro, Exemplar, Usuario, Emprestimo
    l = client.post("/livros", json={
        "titulo": "Clean Architecture", "autor": "Robert Martin", "isbn": "978-0134494166", "ano": 2017, "area_conhecimento": "Engenharia de Software"
    }).json()
    ex = client.post("/exemplares", json={"livro_id": l["id"], "codigo_tombo": "CA-01"}).json()
    u = client.post("/usuarios", json={"nome": "Dev", "email": "dev@clean.com", "matricula": "DEV01", "categoria": "aluno"}).json()

    # Empréstimo ativo
    emp = client.post("/emprestimos", json={"usuario_id": u["id"], "exemplar_id": ex["id"]}).json()

    # Tentar deletar usuário com empréstimo -> 400
    res_del_u = client.delete(f"/usuarios/{u['id']}")
    assert res_del_u.status_code == 400
    assert "histórico de empréstimos" in res_del_u.json()["detail"].lower()

    # Tentar deletar exemplar com empréstimo -> 400
    res_del_ex = client.delete(f"/exemplares/{ex['id']}")
    assert res_del_ex.status_code == 400
    assert "histórico de empréstimos" in res_del_ex.json()["detail"].lower()

    # Tentar deletar livro com exemplar com empréstimo -> 400
    res_del_l = client.delete(f"/livros/{l['id']}")
    assert res_del_l.status_code == 400
    assert "histórico de empréstimos" in res_del_l.json()["detail"].lower()

    # Criar entidades sem empréstimos para testar deleção 204
    l_vazio = client.post("/livros", json={
        "titulo": "Livro Sem Empréstimo", "autor": "Autor", "isbn": "978-85-000-1111-1", "ano": 2022, "area_conhecimento": "Geral"
    }).json()
    ex_vazio = client.post("/exemplares", json={"livro_id": l_vazio["id"], "codigo_tombo": "VAZIO-01"}).json()
    u_vazio = client.post("/usuarios", json={"nome": "User Vazio", "email": "vazio@clean.com", "matricula": "VAZIO01", "categoria": "aluno"}).json()

    # Deleção sem empréstimos funciona perfeitamente (204)
    assert client.delete(f"/exemplares/{ex_vazio['id']}").status_code == 204
    assert client.delete(f"/livros/{l_vazio['id']}").status_code == 204
    assert client.delete(f"/usuarios/{u_vazio['id']}").status_code == 204

def test_limite_professor_8_exemplares(client):
    l = client.post("/livros", json={
        "titulo": "Livro de Pesquisa", "autor": "Pesquisador", "isbn": "978-85-999-0001-0", "ano": 2024, "area_conhecimento": "Ciência"
    }).json()

    prof = client.post("/usuarios", json={
        "nome": "Professor Pesquisador", "email": "pesq@prof.edu.br", "matricula": "PROF_PESQ", "categoria": "professor"
    }).json()

    exemplares = []
    for i in range(1, 10):
        res_ex = client.post("/exemplares", json={"livro_id": l["id"], "codigo_tombo": f"TOMBO-PESQ-{i}"})
        exemplares.append(res_ex.json()["id"])

    # Professor pode pegar até 8 exemplares
    for i in range(8):
        res_emp = client.post("/emprestimos", json={"usuario_id": prof["id"], "exemplar_id": exemplares[i]})
        assert res_emp.status_code == 201

    # O 9º exemplar deve ser negado (limite = 8)
    res_emp9 = client.post("/emprestimos", json={"usuario_id": prof["id"], "exemplar_id": exemplares[8]})
    assert res_emp9.status_code == 400
    assert "limite de 8 exemplares" in res_emp9.json()["detail"]

def test_retirada_de_exemplar_reservado_por_proprio_usuario(client):
    l = client.post("/livros", json={
        "titulo": "Sistemas Distribuídos", "autor": "Coulouris", "isbn": "978-85-8260-053-5", "ano": 2013, "area_conhecimento": "Computação"
    }).json()
    ex = client.post("/exemplares", json={"livro_id": l["id"], "codigo_tombo": "SD-01"}).json()

    u1 = client.post("/usuarios", json={"nome": "U1", "email": "u1@sd.com", "matricula": "SD01", "categoria": "aluno"}).json()
    u2 = client.post("/usuarios", json={"nome": "U2", "email": "u2@sd.com", "matricula": "SD02", "categoria": "aluno"}).json()

    # u1 pega o exemplar
    emp1 = client.post("/emprestimos", json={"usuario_id": u1["id"], "exemplar_id": ex["id"]}).json()

    # u2 reserva o livro
    res = client.post("/reservas", json={"usuario_id": u2["id"], "livro_id": l["id"]}).json()

    # u1 devolve -> exemplar passa a ser 'reservado' para u2 com reserva 'disponivel'
    client.post(f"/emprestimos/{emp1['id']}/devolver")

    ex_status = client.get(f"/exemplares/{ex['id']}").json()
    assert ex_status["estado"] == "reservado"

    # u2 retira o exemplar reservado para si -> sucesso!
    res_emp2 = client.post("/emprestimos", json={"usuario_id": u2["id"], "exemplar_id": ex["id"]})
    assert res_emp2.status_code == 201

    # Reserva de u2 foi concluída e não está mais na fila
    fila = client.get(f"/livros/{l['id']}/reservas").json()
    assert len(fila) == 0

def test_tentativa_devolucao_duplicada(client):
    l = client.post("/livros", json={
        "titulo": "Refactoring", "autor": "Martin Fowler", "isbn": "978-0134757599", "ano": 2018, "area_conhecimento": "Engenharia de Software"
    }).json()
    ex = client.post("/exemplares", json={"livro_id": l["id"], "codigo_tombo": "REF-01"}).json()
    u = client.post("/usuarios", json={"nome": "Fowler Fan", "email": "fowler@ref.com", "matricula": "REF01", "categoria": "aluno"}).json()

    emp = client.post("/emprestimos", json={"usuario_id": u["id"], "exemplar_id": ex["id"]}).json()

    # 1ª devolução
    res1 = client.post(f"/emprestimos/{emp['id']}/devolver")
    assert res1.status_code == 200

    # 2ª devolução -> 400
    res2 = client.post(f"/emprestimos/{emp['id']}/devolver")
    assert res2.status_code == 400
    assert "já foi devolvido" in res2.json()["detail"].lower()

def test_pagar_multa_perdoada(client):
    # Professor com atraso <= 2 dias tem multa perdoada automaticamente
    l = client.post("/livros", json={
        "titulo": "Livro de Teste Multa", "autor": "Autor", "isbn": "978-85-000-0099-9", "ano": 2020, "area_conhecimento": "Geral"
    }).json()
    ex = client.post("/exemplares", json={"livro_id": l["id"], "codigo_tombo": "TM-01"}).json()
    prof = client.post("/usuarios", json={"nome": "Professor X", "email": "x@prof.com", "matricula": "PX01", "categoria": "professor"}).json()

    emp = client.post("/emprestimos", json={
        "usuario_id": prof["id"],
        "exemplar_id": ex["id"],
        "data_retirada": "2026-10-01T10:00:00"
    }).json()

    # Devolve com 1 dia de atraso (30 dias prev = 31/10. Dev = 01/11 -> 1 dia atraso)
    client.post(f"/emprestimos/{emp['id']}/devolver", json={"data_devolucao": "2026-11-01T10:00:00"})

    multas = client.get(f"/usuarios/{prof['id']}/multas").json()
    assert len(multas) == 1
    assert multas[0]["estado"] == "perdoada"

    # Tentar pagar multa perdoada -> 400
    res_pag = client.post(f"/multas/{multas[0]['id']}/pagar")
    assert res_pag.status_code == 400
    assert "já foi perdoada" in res_pag.json()["detail"].lower()
