from datetime import datetime, timedelta

def test_regra_1_restricoes_emprestimo(client):
    livro = client.post("/livros", json={
        "titulo": "Compiladores", "autor": "Aho", "isbn": "978-85-7780-723-9", "ano": 2008, "area_conhecimento": "Computação"
    }).json()
    ex1 = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "TC-01"}).json()
    ex2 = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "TC-02"}).json()

    # Usuário suspenso
    user_susp = client.post("/usuarios", json={
        "nome": "Suspenso", "email": "susp@test.com", "matricula": "S01", "categoria": "aluno"
    }).json()
    client.put(f"/usuarios/{user_susp['id']}", json={
        "situacao": "suspenso",
        "data_fim_suspensao": "2030-01-01T00:00:00"
    })

    res = client.post("/emprestimos", json={"usuario_id": user_susp["id"], "exemplar_id": ex1["id"]})
    assert res.status_code == 400
    assert "suspenso" in res.json()["detail"].lower()

    # Usuário com multa aberta
    user_multa = client.post("/usuarios", json={
        "nome": "Multado", "email": "multa@test.com", "matricula": "M01", "categoria": "aluno"
    }).json()
    # Empréstimo com atraso para gerar multa
    emp_m = client.post("/emprestimos", json={
        "usuario_id": user_multa["id"],
        "exemplar_id": ex1["id"],
        "data_retirada": "2026-10-01T10:00:00"
    }).json()
    # Devolver com 5 dias de atraso
    client.post(f"/emprestimos/{emp_m['id']}/devolver", json={
        "data_devolucao": "2026-10-13T10:00:00"
    })
    # Tentar novo empréstimo com multa aberta
    res_com_multa = client.post("/emprestimos", json={"usuario_id": user_multa["id"], "exemplar_id": ex2["id"]})
    assert res_com_multa.status_code == 400
    assert "multa" in res_com_multa.json()["detail"].lower()

def test_regra_2_suspensao_por_atraso_superior_15_dias(client):
    livro = client.post("/livros", json={
        "titulo": "Redes", "autor": "Tanenbaum", "isbn": "978-85-430-0567-6", "ano": 2011, "area_conhecimento": "Computação"
    }).json()
    ex = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "TR-01"}).json()

    aluno = client.post("/usuarios", json={
        "nome": "Atrasado", "email": "atr@test.com", "matricula": "ATR01", "categoria": "aluno"
    }).json()

    # Prazo de aluno = 7 dias. Retirada: 01/10/2026 -> Prevista: 08/10/2026.
    emp = client.post("/emprestimos", json={
        "usuario_id": aluno["id"],
        "exemplar_id": ex["id"],
        "data_retirada": "2026-10-01T10:00:00"
    }).json()

    # Devolução em 28/10/2026 (20 dias de atraso, que é > 15 dias)
    # Suspensão deve durar o dobro dos dias de atraso = 20 * 2 = 40 dias
    res_dev = client.post(f"/emprestimos/{emp['id']}/devolver", json={
        "data_devolucao": "2026-10-28T10:00:00"
    })
    assert res_dev.status_code == 200

    user_updated = client.get(f"/usuarios/{aluno['id']}").json()
    assert user_updated["situacao"] == "suspenso"
    assert user_updated["data_fim_suspensao"] is not None

    dt_dev = datetime.fromisoformat("2026-10-28T10:00:00")
    dt_fim = datetime.fromisoformat(user_updated["data_fim_suspensao"])
    dias_suspensao = (dt_fim.date() - dt_dev.date()).days
    assert dias_suspensao == 40

def test_regra_3_renovacao_regras(client):
    livro = client.post("/livros", json={
        "titulo": "Sistemas Operacionais", "autor": "Silberschatz", "isbn": "978-85-216-3045-6", "ano": 2015, "area_conhecimento": "Computação"
    }).json()
    ex = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "TSO-01"}).json()

    # Aluno: pode renovar 2 vezes
    aluno = client.post("/usuarios", json={
        "nome": "Renovador", "email": "ren@test.com", "matricula": "REN01", "categoria": "aluno"
    }).json()
    outro_aluno = client.post("/usuarios", json={
        "nome": "Esperando", "email": "esp@test.com", "matricula": "ESP01", "categoria": "aluno"
    }).json()

    emp = client.post("/emprestimos", json={
        "usuario_id": aluno["id"],
        "exemplar_id": ex["id"],
        "data_retirada": datetime.now().isoformat()
    }).json()

    # 1ª renovação: sucesso
    res_ren1 = client.post(f"/emprestimos/{emp['id']}/renovar")
    assert res_ren1.status_code == 200
    assert res_ren1.json()["numero_renovacoes"] == 1

    # 2ª renovação: sucesso
    res_ren2 = client.post(f"/emprestimos/{emp['id']}/renovar")
    assert res_ren2.status_code == 200
    assert res_ren2.json()["numero_renovacoes"] == 2

    # 3ª renovação: negada (limite da categoria atingido)
    res_ren3 = client.post(f"/emprestimos/{emp['id']}/renovar")
    assert res_ren3.status_code == 400
    assert "limite de 2 renovações atingido" in res_ren3.json()["detail"]

    # Teste de renovação com fila de reserva
    ex2 = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "TSO-02"}).json()
    prof = client.post("/usuarios", json={
        "nome": "Prof", "email": "prof_ren@test.com", "matricula": "PREN01", "categoria": "professor"
    }).json()
    emp2 = client.post("/emprestimos", json={
        "usuario_id": prof["id"],
        "exemplar_id": ex2["id"],
        "data_retirada": datetime.now().isoformat()
    }).json()

    # Outro aluno reserva o livro
    client.post("/reservas", json={"usuario_id": outro_aluno["id"], "livro_id": livro["id"]})

    # Professor tenta renovar mas há fila de reserva
    res_ren_prof = client.post(f"/emprestimos/{emp2['id']}/renovar")
    assert res_ren_prof.status_code == 400
    assert "fila de reserva" in res_ren_prof.json()["detail"].lower()

    # Teste visitante: 0 renovações permitidas
    livro_vis = client.post("/livros", json={
        "titulo": "Livro Visitante", "autor": "Autor V", "isbn": "978-85-000-0001-1", "ano": 2021, "area_conhecimento": "Geral"
    }).json()
    ex3 = client.post("/exemplares", json={"livro_id": livro_vis["id"], "codigo_tombo": "TVIS-01"}).json()
    vis = client.post("/usuarios", json={
        "nome": "Vis", "email": "vis_ren@test.com", "matricula": "VREN01", "categoria": "visitante"
    }).json()
    emp3 = client.post("/emprestimos", json={
        "usuario_id": vis["id"],
        "exemplar_id": ex3["id"],
        "data_retirada": datetime.now().isoformat()
    }).json()
    res_ren_vis = client.post(f"/emprestimos/{emp3['id']}/renovar")
    assert res_ren_vis.status_code == 400
    assert "limite de 0 renovações" in res_ren_vis.json()["detail"]

def test_regra_4_fila_de_reservas_e_expiracao(client):
    livro = client.post("/livros", json={
        "titulo": "Inteligência Artificial", "autor": "Russell & Norvig", "isbn": "978-85-352-3701-6", "ano": 2013, "area_conhecimento": "Computação"
    }).json()
    ex = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "TIA-01"}).json()

    u1 = client.post("/usuarios", json={"nome": "U1", "email": "u1@t.com", "matricula": "U01", "categoria": "aluno"}).json()["id"]
    u2 = client.post("/usuarios", json={"nome": "U2", "email": "u2@t.com", "matricula": "U02", "categoria": "aluno"}).json()["id"]
    u3 = client.post("/usuarios", json={"nome": "U3", "email": "u3@t.com", "matricula": "U03", "categoria": "aluno"}).json()["id"]

    # Empresta exemplar para u1 em 01/11
    emp = client.post("/emprestimos", json={
        "usuario_id": u1,
        "exemplar_id": ex["id"],
        "data_retirada": "2026-11-01T08:00:00"
    }).json()

    # u2 reserva o livro (deve ser pos 1)
    res_u2 = client.post("/reservas", json={"usuario_id": u2, "livro_id": livro["id"]}).json()
    assert res_u2["posicao_fila"] == 1
    assert res_u2["estado"] == "aguardando"

    # u3 reserva o livro (deve ser pos 2)
    res_u3 = client.post("/reservas", json={"usuario_id": u3, "livro_id": livro["id"]}).json()
    assert res_u3["posicao_fila"] == 2
    assert res_u3["estado"] == "aguardando"

    # u1 devolve o exemplar em 01/11 10:00: primeiro da fila (u2) passa para 'disponivel' com 48h
    dt_dev = datetime(2026, 11, 1, 10, 0, 0)
    client.post(f"/emprestimos/{emp['id']}/devolver", json={"data_devolucao": dt_dev.isoformat()})

    res_u2_updated = client.get(f"/reservas/{res_u2['id']}").json()
    assert res_u2_updated["estado"] == "disponivel"
    assert res_u2_updated["data_limite_retirada"] is not None
    dt_limite = datetime.fromisoformat(res_u2_updated["data_limite_retirada"])
    assert (dt_limite - dt_dev).total_seconds() == 48 * 3600

    # u3 tenta pegar o livro que está reservado para u2 dentro da janela de 48h (em 01/11 12:00) -> negado
    res_tentativa = client.post("/emprestimos", json={
        "usuario_id": u3,
        "exemplar_id": ex["id"],
        "data_retirada": "2026-11-01T12:00:00"
    })
    assert res_tentativa.status_code == 400

    # Quando u2 cancela sua reserva, o próximo da fila (u3) passa automaticamente a 'disponivel'
    client.post(f"/reservas/{res_u2['id']}/cancelar")
    res_u3_updated = client.get(f"/reservas/{res_u3['id']}").json()
    assert res_u3_updated["estado"] == "disponivel"
    assert res_u3_updated["data_limite_retirada"] is not None

def test_regra_5_calculo_multas_por_categoria(client):
    livro = client.post("/livros", json={
        "titulo": "Física I", "autor": "Halliday", "isbn": "978-85-216-1903-1", "ano": 2012, "area_conhecimento": "Física"
    }).json()
    ex1 = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "FIS-01"}).json()
    ex2 = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "FIS-02"}).json()
    ex3 = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "FIS-03"}).json()
    ex4 = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "FIS-04"}).json()
    ex5 = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "FIS-05"}).json()

    aluno = client.post("/usuarios", json={"nome": "A", "email": "a@f.com", "matricula": "A_F", "categoria": "aluno"}).json()["id"]
    prof = client.post("/usuarios", json={"nome": "P", "email": "p@f.com", "matricula": "P_F", "categoria": "professor"}).json()["id"]
    vis = client.post("/usuarios", json={"nome": "V", "email": "v@f.com", "matricula": "V_F", "categoria": "visitante"}).json()["id"]

    # 1. Aluno: R$ 1,00/dia; 5 dias atraso = R$ 5,00
    # Prazo: 7 dias. Retirada 01/11 -> Prevista 08/11. Devolução 13/11 (5 dias atraso)
    emp_a = client.post("/emprestimos", json={"usuario_id": aluno, "exemplar_id": ex1["id"], "data_retirada": "2026-11-01T10:00:00"}).json()
    client.post(f"/emprestimos/{emp_a['id']}/devolver", json={"data_devolucao": "2026-11-13T10:00:00"})
    multas_a = client.get(f"/usuarios/{aluno}/multas").json()
    assert len(multas_a) == 1
    assert float(multas_a[0]["valor"]) == 5.00
    assert multas_a[0]["estado"] == "aberta"

    # Pagar a multa do aluno para permitir novo empréstimo (Regra 1)
    client.post(f"/multas/{multas_a[0]['id']}/pagar")

    # Aluno: teto R$ 30,00 (ex: 40 dias atraso)
    # Retirada 01/08 -> Prevista 08/08. Devolução 17/09 (40 dias atraso)
    emp_a2 = client.post("/emprestimos", json={"usuario_id": aluno, "exemplar_id": ex2["id"], "data_retirada": "2026-08-01T10:00:00"}).json()
    client.post(f"/emprestimos/{emp_a2['id']}/devolver", json={"data_devolucao": "2026-09-17T10:00:00"})
    multas_a_all = client.get(f"/usuarios/{aluno}/multas").json()
    assert float(multas_a_all[1]["valor"]) == 30.00

    # 2. Professor: atraso de 2 dias é perdoado automaticamente
    # Prazo: 30 dias. Retirada 01/10 -> Prevista 31/10. Devolução 02/11 (2 dias atraso)
    emp_p1 = client.post("/emprestimos", json={"usuario_id": prof, "exemplar_id": ex3["id"], "data_retirada": "2026-10-01T10:00:00"}).json()
    client.post(f"/emprestimos/{emp_p1['id']}/devolver", json={"data_devolucao": "2026-11-02T10:00:00"})
    multas_p = client.get(f"/usuarios/{prof}/multas").json()
    assert len(multas_p) == 1
    assert multas_p[0]["estado"] == "perdoada"

    # Professor: atraso de 4 dias = R$ 2,00 (4 * 0,50) aberta
    emp_p2 = client.post("/emprestimos", json={"usuario_id": prof, "exemplar_id": ex4["id"], "data_retirada": "2026-10-01T10:00:00"}).json()
    client.post(f"/emprestimos/{emp_p2['id']}/devolver", json={"data_devolucao": "2026-11-04T10:00:00"})
    multas_p_all = client.get(f"/usuarios/{prof}/multas").json()
    assert float(multas_p_all[1]["valor"]) == 2.00
    assert multas_p_all[1]["estado"] == "aberta"

    # 3. Visitante: R$ 2,00/dia; teto R$ 20,00
    # Prazo: 3 dias. Retirada 01/11 -> Prevista 04/11. Devolução 07/11 (3 dias atraso = R$ 6,00)
    emp_v = client.post("/emprestimos", json={"usuario_id": vis, "exemplar_id": ex5["id"], "data_retirada": "2026-11-01T10:00:00"}).json()
    client.post(f"/emprestimos/{emp_v['id']}/devolver", json={"data_devolucao": "2026-11-07T10:00:00"})
    multas_v = client.get(f"/usuarios/{vis}/multas").json()
    assert len(multas_v) == 1
    assert float(multas_v[0]["valor"]) == 6.00

def test_regra_6_exemplar_reparo_ou_baixado(client):
    livro = client.post("/livros", json={
        "titulo": "Química Geral", "autor": "Kotz", "isbn": "978-85-221-1828-1", "ano": 2015, "area_conhecimento": "Química"
    }).json()
    ex1 = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "Q-01", "estado": "em_reparo"}).json()

    user = client.post("/usuarios", json={"nome": "U", "email": "u@q.com", "matricula": "UQ01", "categoria": "aluno"}).json()["id"]

    # Tentar emprestar exemplar em reparo -> negado
    res_emp = client.post("/emprestimos", json={"usuario_id": user, "exemplar_id": ex1["id"]})
    assert res_emp.status_code == 400

    # Tentar reservar livro cujo único exemplar está em reparo -> negado
    res_res = client.post("/reservas", json={"usuario_id": user, "livro_id": livro["id"]})
    assert res_res.status_code == 400

    # Adicionar exemplar disponível
    ex2 = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "Q-02", "estado": "disponivel"}).json()

    # Agora a reserva é permitida
    res_res2 = client.post("/reservas", json={"usuario_id": user, "livro_id": livro["id"]})
    assert res_res2.status_code == 201

    # Se o único exemplar disponível for baixado (e o outro em reparo), todas as reservas daquele livro são canceladas
    client.put(f"/exemplares/{ex2['id']}", json={"estado": "baixado"})
    res_cancelada = client.get(f"/reservas/{res_res2.json()['id']}").json()
    assert res_cancelada["estado"] == "cancelada"

def test_regra_7_atraso_superior_60_dias(client):
    livro = client.post("/livros", json={
        "titulo": "Cálculo I", "autor": "Stewart", "isbn": "978-85-221-1258-6", "ano": 2013, "area_conhecimento": "Matemática"
    }).json()
    ex = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "CALC-01"}).json()

    aluno = client.post("/usuarios", json={"nome": "Esquecido", "email": "esq@test.com", "matricula": "ESQ01", "categoria": "aluno"}).json()["id"]

    # Retirada 01/01/2026 -> Prevista 08/01/2026
    emp = client.post("/emprestimos", json={
        "usuario_id": aluno,
        "exemplar_id": ex["id"],
        "data_retirada": "2026-01-01T10:00:00"
    }).json()

    # Devolução 65 dias após o prazo previsto: 14/03/2026 (65 dias de atraso > 60)
    res_dev = client.post(f"/emprestimos/{emp['id']}/devolver", json={
        "data_devolucao": "2026-03-14T10:00:00"
    })
    assert res_dev.status_code == 200

    # Exemplar deve estar baixado
    ex_updated = client.get(f"/exemplares/{ex['id']}").json()
    assert ex_updated["estado"] == "baixado"

    # Multa deve ser no valor do teto da categoria do aluno (R$ 30,00)
    multas = client.get(f"/usuarios/{aluno}/multas").json()
    assert len(multas) == 1
    assert float(multas[0]["valor"]) == 30.00
    assert multas[0]["estado"] == "aberta"
