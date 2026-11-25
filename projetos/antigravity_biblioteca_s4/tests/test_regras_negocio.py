from datetime import datetime, timedelta
from fastapi import status


def _criar_cenario_base(client):
    # Usuários
    u_aluno = client.post(
        "/usuarios",
        json={"nome": "Aluno Teste", "email": "aluno@teste.com", "matricula": "A001", "categoria": "aluno"},
    ).json()

    u_prof = client.post(
        "/usuarios",
        json={"nome": "Prof Teste", "email": "prof@teste.com", "matricula": "P001", "categoria": "professor"},
    ).json()

    u_vis = client.post(
        "/usuarios",
        json={"nome": "Vis Teste", "email": "vis@teste.com", "matricula": "V001", "categoria": "visitante"},
    ).json()

    # Livro e Exemplares
    livro = client.post(
        "/livros",
        json={
            "titulo": "Engenharia de Software",
            "autor": "Ian Sommerville",
            "isbn": "978-85-7780-600-0",
            "ano": 2011,
            "area_conhecimento": "Engenharia",
        },
    ).json()

    ex1 = client.post(
        "/exemplares",
        json={"livro_id": livro["id"], "codigo_tombo": "ENG-01", "estado": "disponivel"},
    ).json()

    ex2 = client.post(
        "/exemplares",
        json={"livro_id": livro["id"], "codigo_tombo": "ENG-02", "estado": "disponivel"},
    ).json()

    return {
        "aluno": u_aluno,
        "professor": u_prof,
        "visitante": u_vis,
        "livro": livro,
        "ex1": ex1,
        "ex2": ex2,
    }


def test_regras_categorias_prazos_e_limites(client):
    """Verifica limites de exemplares e prazos por categoria."""
    cenario = _criar_cenario_base(client)
    agora = datetime.now()

    # Aluno: prazo 7 dias
    resp_emp_aluno = client.post(
        "/emprestimos",
        json={
            "usuario_id": cenario["aluno"]["id"],
            "exemplar_id": cenario["ex1"]["id"],
            "data_retirada": agora.isoformat(),
        },
    )
    assert resp_emp_aluno.status_code == status.HTTP_201_CREATED
    data_prevista = datetime.fromisoformat(resp_emp_aluno.json()["data_prevista"])
    assert (data_prevista.date() - agora.date()).days == 7

    # Visitante: limite de 1 exemplar
    resp_emp_vis1 = client.post(
        "/emprestimos",
        json={
            "usuario_id": cenario["visitante"]["id"],
            "exemplar_id": cenario["ex2"]["id"],
            "data_retirada": agora.isoformat(),
        },
    )
    assert resp_emp_vis1.status_code == status.HTTP_201_CREATED
    data_prevista_vis = datetime.fromisoformat(resp_emp_vis1.json()["data_prevista"])
    assert (data_prevista_vis.date() - agora.date()).days == 3  # Prazo visitante: 3 dias

    # Criar outro exemplar para tentar estourar o limite do visitante
    ex3 = client.post(
        "/exemplares",
        json={"livro_id": cenario["livro"]["id"], "codigo_tombo": "ENG-03", "estado": "disponivel"},
    ).json()

    # Tentativa de segundo empréstimo para visitante deve falhar (limite = 1)
    resp_emp_vis2 = client.post(
        "/emprestimos",
        json={
            "usuario_id": cenario["visitante"]["id"],
            "exemplar_id": ex3["id"],
            "data_retirada": agora.isoformat(),
        },
    )
    assert resp_emp_vis2.status_code == status.HTTP_400_BAD_REQUEST
    assert "limite de 1 exemplares atingido" in resp_emp_vis2.json()["detail"]


def test_regra_1_bloqueio_por_multa_aberta_ou_usuario_suspenso(client):
    """Regra 1: Empréstimo só é permitido a usuário ativo, sem multa aberta e abaixo do limite."""
    cenario = _criar_cenario_base(client)
    agora = datetime.now() - timedelta(days=15)

    # Empresta ex1 para aluno no passado
    emp = client.post(
        "/emprestimos",
        json={
            "usuario_id": cenario["aluno"]["id"],
            "exemplar_id": cenario["ex1"]["id"],
            "data_retirada": agora.isoformat(),
        },
    ).json()

    # Devolve com atraso de 5 dias -> gera multa aberta de R$ 5,00
    data_devolucao = agora + timedelta(days=7 + 5)
    client.post(
        f"/emprestimos/{emp['id']}/devolver",
        json={"data_devolucao": data_devolucao.isoformat()},
    )

    # Verifica multa gerada
    resp_multas = client.get(f"/usuarios/{cenario['aluno']['id']}/multas")
    assert resp_multas.status_code == status.HTTP_200_OK
    multas = resp_multas.json()
    assert len(multas) == 1
    assert multas[0]["valor"] == 5.0
    assert multas[0]["estado"] == "aberta"
    multa_id = multas[0]["id"]

    # Tentativa de novo empréstimo com multa aberta deve ser negada
    resp_novo = client.post(
        "/emprestimos",
        json={
            "usuario_id": cenario["aluno"]["id"],
            "exemplar_id": cenario["ex2"]["id"],
            "data_retirada": datetime.now().isoformat(),
        },
    )
    assert resp_novo.status_code == status.HTTP_400_BAD_REQUEST
    assert "multas em aberto" in resp_novo.json()["detail"]

    # Paga a multa
    resp_pagar = client.post(f"/multas/{multa_id}/pagar")
    assert resp_pagar.status_code == status.HTTP_200_OK
    assert resp_pagar.json()["estado"] == "paga"

    # Agora o empréstimo deve ser permitido!
    resp_novo_apos_pagar = client.post(
        "/emprestimos",
        json={
            "usuario_id": cenario["aluno"]["id"],
            "exemplar_id": cenario["ex2"]["id"],
            "data_retirada": datetime.now().isoformat(),
        },
    )
    assert resp_novo_apos_pagar.status_code == status.HTTP_201_CREATED


def test_regra_2_suspensao_automatica_atraso_superior_15_dias(client):
    """Regra 2: Usuário com atraso superior a 15 dias é automaticamente suspenso e a suspensão dura o dobro."""
    cenario = _criar_cenario_base(client)
    hoje = datetime.now()
    # Empréstimo feito há 23 dias: prazo 7 dias, então data prevista foi há 16 dias
    data_retirada = hoje - timedelta(days=23)

    emp = client.post(
        "/emprestimos",
        json={
            "usuario_id": cenario["aluno"]["id"],
            "exemplar_id": cenario["ex1"]["id"],
            "data_retirada": data_retirada.isoformat(),
        },
    ).json()

    # Devolve hoje: atraso de 16 dias (16 > 15)
    data_devolucao = hoje
    client.post(
        f"/emprestimos/{emp['id']}/devolver",
        json={"data_devolucao": data_devolucao.isoformat()},
    )

    # Verifica situação do usuário: deve estar suspenso por 2 * 16 = 32 dias no futuro
    user_resp = client.get(f"/usuarios/{cenario['aluno']['id']}")
    assert user_resp.status_code == status.HTTP_200_OK
    user_data = user_resp.json()
    assert user_data["situacao"] == "suspenso"
    assert user_data["data_fim_suspensao"] is not None
    data_fim = datetime.fromisoformat(user_data["data_fim_suspensao"])
    assert (data_fim.date() - data_devolucao.date()).days == 32


def test_regra_3_renovacao_regras(client):
    """Regra 3: Renovação negada se houver fila de reserva, atraso ou limite de renovações atingido."""
    cenario = _criar_cenario_base(client)
    agora = datetime.now()

    # Empréstimo para aluno (limite: 2 renovações)
    emp = client.post(
        "/emprestimos",
        json={
            "usuario_id": cenario["aluno"]["id"],
            "exemplar_id": cenario["ex1"]["id"],
            "data_retirada": agora.isoformat(),
        },
    ).json()

    # 1ª renovação: sucesso (data prevista + 7 dias)
    resp_ren1 = client.post(f"/emprestimos/{emp['id']}/renovar")
    assert resp_ren1.status_code == status.HTTP_200_OK
    assert resp_ren1.json()["numero_de_renovacoes"] == 1
    prevista1 = datetime.fromisoformat(resp_ren1.json()["data_prevista"])
    assert (prevista1.date() - agora.date()).days == 14

    # 2ª renovação: sucesso
    resp_ren2 = client.post(f"/emprestimos/{emp['id']}/renovar")
    assert resp_ren2.status_code == status.HTTP_200_OK
    assert resp_ren2.json()["numero_de_renovacoes"] == 2

    # 3ª renovação: limite atingido (negada)
    resp_ren3 = client.post(f"/emprestimos/{emp['id']}/renovar")
    assert resp_ren3.status_code == status.HTTP_400_BAD_REQUEST
    assert "limite de 2 renovações atingido" in resp_ren3.json()["detail"]

    # Teste de renovação negada por reserva na fila:
    # Professor pega ex2
    emp_prof = client.post(
        "/emprestimos",
        json={
            "usuario_id": cenario["professor"]["id"],
            "exemplar_id": cenario["ex2"]["id"],
            "data_retirada": agora.isoformat(),
        },
    ).json()

    # Visitante faz reserva do mesmo livro
    resp_res = client.post(
        "/reservas",
        json={
            "usuario_id": cenario["visitante"]["id"],
            "livro_id": cenario["livro"]["id"],
        },
    )
    assert resp_res.status_code == status.HTTP_201_CREATED

    # Professor tenta renovar: deve ser negada por ter reserva na fila
    resp_ren_prof = client.post(f"/emprestimos/{emp_prof['id']}/renovar")
    assert resp_ren_prof.status_code == status.HTTP_400_BAD_REQUEST
    assert "fila de reserva" in resp_ren_prof.json()["detail"]


def test_regra_4_fila_de_reserva_e_expiracao_48h(client):
    """Regra 4: Fila FIFO, exemplar devolvido passa 1º para disponível com 48h; esgotado prazo, expira e passa ao próximo."""
    cenario = _criar_cenario_base(client)
    agora = datetime.now() - timedelta(days=10)

    # Empresta ex1 para Aluno
    client.post(
        "/emprestimos",
        json={
            "usuario_id": cenario["aluno"]["id"],
            "exemplar_id": cenario["ex1"]["id"],
            "data_retirada": agora.isoformat(),
        },
    )
    # Baixa ex2 para garantir que ex1 seja o único exemplar ativo
    client.put(f"/exemplares/{cenario['ex2']['id']}", json={"estado": "baixado"})

    # Professor reserva o livro (fila pos 1)
    res_prof = client.post(
        "/reservas",
        json={"usuario_id": cenario["professor"]["id"], "livro_id": cenario["livro"]["id"]},
    ).json()
    assert res_prof["posicao_na_fila"] == 1
    assert res_prof["estado"] == "aguardando"

    # Visitante reserva o livro (fila pos 2)
    res_vis = client.post(
        "/reservas",
        json={"usuario_id": cenario["visitante"]["id"], "livro_id": cenario["livro"]["id"]},
    ).json()
    assert res_vis["posicao_na_fila"] == 2
    assert res_vis["estado"] == "aguardando"

    # Aluno devolve o exemplar ex1 há 3 dias (mais de 48h atrás)
    dev_time = datetime.now() - timedelta(days=3)
    emp_aluno = client.get(f"/usuarios/{cenario['aluno']['id']}/emprestimos").json()[0]
    client.post(
        f"/emprestimos/{emp_aluno['id']}/devolver",
        json={"data_devolucao": dev_time.isoformat()},
    )

    # Processa expirações (já que passou 72h > 48h da devolução)
    client.post("/reservas/processar-expiracoes")

    # Verifica que res_prof expirou
    res_prof_expirada = client.get(f"/reservas/{res_prof['id']}").json()
    assert res_prof_expirada["estado"] == "expirada"

    # Verifica que res_vis agora passou a 'disponivel'
    res_vis_atualizada = client.get(f"/reservas/{res_vis['id']}").json()
    assert res_vis_atualizada["estado"] == "disponivel"


def test_regra_5_multa_e_perdao_professor(client):
    """Regra 5: Multa diária, limites por categoria e perdão de professor se atraso <= 2 dias."""
    cenario = _criar_cenario_base(client)
    agora = datetime.now() - timedelta(days=50)

    # Professor com 2 dias de atraso (30 dias de prazo + 2 dias) -> MULTA PERDOADA
    emp_prof = client.post(
        "/emprestimos",
        json={
            "usuario_id": cenario["professor"]["id"],
            "exemplar_id": cenario["ex1"]["id"],
            "data_retirada": agora.isoformat(),
        },
    ).json()

    dev_prof = agora + timedelta(days=30 + 2)
    client.post(
        f"/emprestimos/{emp_prof['id']}/devolver",
        json={"data_devolucao": dev_prof.isoformat()},
    )

    multas_prof = client.get(f"/usuarios/{cenario['professor']['id']}/multas").json()
    assert len(multas_prof) == 1
    assert multas_prof[0]["estado"] == "perdoada"
    assert multas_prof[0]["valor"] == 1.0  # 2 dias * 0.50

    # Aluno com 40 dias de atraso -> atinge o teto de R$ 30,00
    emp_aluno = client.post(
        "/emprestimos",
        json={
            "usuario_id": cenario["aluno"]["id"],
            "exemplar_id": cenario["ex2"]["id"],
            "data_retirada": agora.isoformat(),
        },
    ).json()

    dev_aluno = agora + timedelta(days=7 + 40)
    client.post(
        f"/emprestimos/{emp_aluno['id']}/devolver",
        json={"data_devolucao": dev_aluno.isoformat()},
    )

    multas_aluno = client.get(f"/usuarios/{cenario['aluno']['id']}/multas").json()
    assert len(multas_aluno) == 1
    assert multas_aluno[0]["estado"] == "aberta"
    assert multas_aluno[0]["valor"] == 30.0  # Teto do aluno


def test_regra_6_exemplar_reparo_baixado_e_cancelamento_reservas(client):
    """Regra 6: Exemplar em reparo/baixado não pode ser emprestado/reservado; se último baixado, cancela reservas."""
    cenario = _criar_cenario_base(client)

    # Marca ex1 como em_reparo
    client.put(f"/exemplares/{cenario['ex1']['id']}", json={"estado": "em_reparo"})

    # Tentativa de emprestar ex1 deve falhar
    resp_emp = client.post(
        "/emprestimos",
        json={"usuario_id": cenario["aluno"]["id"], "exemplar_id": cenario["ex1"]["id"]},
    )
    assert resp_emp.status_code == status.HTTP_400_BAD_REQUEST
    assert "em reparo" in resp_emp.json()["detail"]

    # Aluno reserva o livro (ex2 ainda está disponivel/ativo)
    res = client.post(
        "/reservas",
        json={"usuario_id": cenario["aluno"]["id"], "livro_id": cenario["livro"]["id"]},
    ).json()
    assert res["estado"] == "aguardando"

    # Baixa o ex1 e baixa o ex2 (último exemplar ativo do livro é baixado)
    client.put(f"/exemplares/{cenario['ex1']['id']}", json={"estado": "baixado"})
    client.put(f"/exemplares/{cenario['ex2']['id']}", json={"estado": "baixado"})

    # Verifica se a reserva foi automaticamente cancelada pela Regra 6
    res_atualizada = client.get(f"/reservas/{res['id']}").json()
    assert res_atualizada["estado"] == "cancelada"


def test_regra_7_atraso_mais_60_dias_marca_baixado_e_multa_teto(client):
    """Regra 7: Devolução com mais de 60 dias de atraso marca exemplar como baixado e gera multa no valor do teto."""
    cenario = _criar_cenario_base(client)
    hoje = datetime.now()
    # Empréstimo feito há 68 dias: prazo 3 dias, portanto atraso de 65 dias
    data_ret = hoje - timedelta(days=68)

    emp_vis = client.post(
        "/emprestimos",
        json={
            "usuario_id": cenario["visitante"]["id"],
            "exemplar_id": cenario["ex1"]["id"],
            "data_retirada": data_ret.isoformat(),
        },
    ).json()

    # Devolve hoje (65 dias de atraso)
    data_dev = hoje
    resp_dev = client.post(
        f"/emprestimos/{emp_vis['id']}/devolver",
        json={"data_devolucao": data_dev.isoformat()},
    )
    assert resp_dev.status_code == status.HTTP_200_OK

    # Exemplar deve estar baixado
    ex_check = client.get(f"/exemplares/{cenario['ex1']['id']}").json()
    assert ex_check["estado"] == "baixado"

    # Multa deve ser exatamente o teto da categoria (Visitante: R$ 20,00)
    multas = client.get(f"/usuarios/{cenario['visitante']['id']}/multas").json()
    assert len(multas) == 1
    assert multas[0]["valor"] == 20.0
    assert multas[0]["estado"] == "aberta"

    # Usuário também deve estar suspenso por 2 * 65 = 130 dias (Regra 2) no futuro
    user_check = client.get(f"/usuarios/{cenario['visitante']['id']}").json()
    assert user_check["situacao"] == "suspenso"
    fim_susp = datetime.fromisoformat(user_check["data_fim_suspensao"])
    assert (fim_susp.date() - data_dev.date()).days == 130
