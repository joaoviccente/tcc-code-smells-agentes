from datetime import datetime, timedelta, timezone
import pytest


def test_regra_1_aluno_inativo_nao_pode_matricular(client):
    """
    Regra 1: A matricula so e permitida a aluno ativo.
    """
    aluno_trancado = client.post("/alunos", json={
        "nome": "Aluno Trancado",
        "matricula": "TR001",
        "email": "trancado@univ.br",
        "categoria": "graduacao",
        "situacao": "trancado"
    }).json()

    aluno_jubilado = client.post("/alunos", json={
        "nome": "Aluno Jubilado",
        "matricula": "JU001",
        "email": "jubilado@univ.br",
        "categoria": "graduacao",
        "situacao": "jubilado"
    }).json()

    d = client.post("/disciplinas", json={
        "codigo": "MAT01",
        "nome": "Matematica Basica",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Matematica"
    }).json()

    t = client.post("/turmas", json={
        "disciplina_id": d["id"],
        "semestre": "2026.1",
        "professor": "Prof Euler",
        "numero_vagas": 20,
        "horario": "SEG 08:00-10:00"
    }).json()

    res1 = client.post("/matriculas", json={"aluno_id": aluno_trancado["id"], "turma_id": t["id"]})
    assert res1.status_code == 400
    assert "ativo" in res1.json()["detail"].lower()

    res2 = client.post("/matriculas", json={"aluno_id": aluno_jubilado["id"], "turma_id": t["id"]})
    assert res2.status_code == 400
    assert "ativo" in res2.json()["detail"].lower()


def test_regra_1_pre_requisito_nao_cumprido(client):
    """
    Regra 1: ...que tenha sido aprovado em todos os pre-requisitos da disciplina segundo o historico.
    """
    d1 = client.post("/disciplinas", json={
        "codigo": "PRQ1",
        "nome": "Programacao 1",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Computacao"
    }).json()

    d2 = client.post("/disciplinas", json={
        "codigo": "PRQ2",
        "nome": "Programacao 2",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Computacao"
    }).json()

    # d1 é pré-requisito de d2
    client.post(f"/disciplinas/{d2['id']}/pre-requisitos", json={"pre_requisito_id": d1["id"]})

    turma_d2 = client.post("/turmas", json={
        "disciplina_id": d2["id"],
        "semestre": "2026.1",
        "professor": "Prof Dijkstra",
        "numero_vagas": 20,
        "horario": "TER 08:00-10:00"
    }).json()

    aluno = client.post("/alunos", json={
        "nome": "Estudante Prog",
        "matricula": "PG001",
        "email": "prog@univ.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }).json()

    # Tentativa de matrícula sem ter cursado o pré-requisito -> 400
    res_sem_prereq = client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": turma_d2["id"]})
    assert res_sem_prereq.status_code == 400
    assert "pré-requisitos" in res_sem_prereq.json()["detail"].lower()

    # Se o aluno foi reprovado no pré-requisito -> ainda não pode matricular
    client.post(f"/alunos/{aluno['id']}/historico", json={
        "aluno_id": aluno["id"],
        "disciplina_id": d1["id"],
        "semestre": "2025.2",
        "nota": 4.0,
        "situacao": "reprovado"
    })
    res_reprovado = client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": turma_d2["id"]})
    assert res_reprovado.status_code == 400

    # Agora registra aprovação no pré-requisito no histórico
    client.post(f"/alunos/{aluno['id']}/historico", json={
        "aluno_id": aluno["id"],
        "disciplina_id": d1["id"],
        "semestre": "2025.2",
        "nota": 8.5,
        "situacao": "aprovado"
    })
    res_aprovado = client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": turma_d2["id"]})
    assert res_aprovado.status_code == 201
    assert res_aprovado.json()["estado"] == "confirmada"


def test_regra_1_limite_creditos_por_categoria(client):
    """
    Graduação: máx 28 créditos por semestre
    Pós: máx 16 créditos por semestre
    Especial: máx 8 créditos por semestre
    """
    # Aluno Especial (limite 8 créditos)
    aluno_esp = client.post("/alunos", json={
        "nome": "Aluno Especial",
        "matricula": "ESP001",
        "email": "especial@univ.br",
        "categoria": "especial",
        "situacao": "ativo"
    }).json()

    # Disciplinas de 4 créditos e 6 créditos
    d_4 = client.post("/disciplinas", json={
        "codigo": "C4_1",
        "nome": "Disciplina 4 Creditos A",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Geral"
    }).json()

    d_6 = client.post("/disciplinas", json={
        "codigo": "C6_1",
        "nome": "Disciplina 6 Creditos",
        "numero_creditos": 6,
        "carga_horaria": 90,
        "departamento": "Geral"
    }).json()

    t_4 = client.post("/turmas", json={
        "disciplina_id": d_4["id"],
        "semestre": "2026.1",
        "professor": "Prof 1",
        "numero_vagas": 20,
        "horario": "SEG 08:00-10:00"
    }).json()

    t_6 = client.post("/turmas", json={
        "disciplina_id": d_6["id"],
        "semestre": "2026.1",
        "professor": "Prof 2",
        "numero_vagas": 20,
        "horario": "TER 08:00-10:00"
    }).json()

    # 1ª matrícula: 4 créditos (acumulado = 4 <= 8) -> OK
    res1 = client.post("/matriculas", json={"aluno_id": aluno_esp["id"], "turma_id": t_4["id"]})
    assert res1.status_code == 201

    # 2ª matrícula: 6 créditos (acumulado = 4 + 6 = 10 > 8) -> 400
    res2 = client.post("/matriculas", json={"aluno_id": aluno_esp["id"], "turma_id": t_6["id"]})
    assert res2.status_code == 400
    assert "limite de créditos" in res2.json()["detail"].lower()


def test_regra_3_tres_reprovacoes_mesma_disciplina_bloqueia(client):
    """
    Regra 3: Aluno reprovado tres vezes na mesma disciplina fica impedido de se matricular nela novamente.
    """
    d = client.post("/disciplinas", json={
        "codigo": "CALCDIF",
        "nome": "Calculo Avancado",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Matematica"
    }).json()

    t = client.post("/turmas", json={
        "disciplina_id": d["id"],
        "semestre": "2026.1",
        "professor": "Prof Leibniz",
        "numero_vagas": 20,
        "horario": "SEG 08:00-10:00"
    }).json()

    aluno = client.post("/alunos", json={
        "nome": "Aluno Reprovado",
        "matricula": "REP001",
        "email": "rep@univ.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }).json()

    # 2 reprovações no histórico -> ainda pode matricular
    for sem in ["2024.1", "2024.2"]:
        client.post(f"/alunos/{aluno['id']}/historico", json={
            "aluno_id": aluno["id"],
            "disciplina_id": d["id"],
            "semestre": sem,
            "nota": 3.0,
            "situacao": "reprovado"
        })

    # Pode solicitar (ainda tem 2)
    res_ok = client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": t["id"]})
    assert res_ok.status_code == 201

    # Remove para testar a 3ª reprovação
    client.post(f"/matriculas/{res_ok.json()['id']}/cancelar")

    # Adiciona a 3ª reprovação no histórico
    client.post(f"/alunos/{aluno['id']}/historico", json={
        "aluno_id": aluno["id"],
        "disciplina_id": d["id"],
        "semestre": "2025.1",
        "nota": 2.0,
        "situacao": "reprovado"
    })

    # Agora tem 3 reprovações -> Bloqueado!
    res_bloqueado = client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": t["id"]})
    assert res_bloqueado.status_code == 400
    assert "3 reprovações" in res_bloqueado.json()["detail"].lower() or "reprovado 3 vezes" in res_bloqueado.json()["detail"].lower()


def test_regra_6_conflito_de_horario_com_outra_turma_confirmada(client):
    """
    Regra 6: Matricula em turma cujo horario conflita com outra turma ja confirmada do aluno e negada.
    """
    d1 = client.post("/disciplinas", json={
        "codigo": "CONF1",
        "nome": "Disciplina 1",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Geral"
    }).json()

    d2 = client.post("/disciplinas", json={
        "codigo": "CONF2",
        "nome": "Disciplina 2",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Geral"
    }).json()

    # Ambas no mesmo horário: SEG 08:00-10:00
    t1 = client.post("/turmas", json={
        "disciplina_id": d1["id"],
        "semestre": "2026.1",
        "professor": "Prof 1",
        "numero_vagas": 20,
        "horario": "SEG 08:00-10:00"
    }).json()

    t2 = client.post("/turmas", json={
        "disciplina_id": d2["id"],
        "semestre": "2026.1",
        "professor": "Prof 2",
        "numero_vagas": 20,
        "horario": "SEG 09:00-11:00"  # Sobrepõe com 08:00-10:00!
    }).json()

    aluno = client.post("/alunos", json={
        "nome": "Aluno Conflito",
        "matricula": "CONF001",
        "email": "conf@univ.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }).json()

    # Confirma em t1
    res1 = client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": t1["id"]})
    assert res1.status_code == 201
    assert res1.json()["estado"] == "confirmada"

    # Tenta matricular em t2 com horário sobreposto -> 409 Conflito
    res2 = client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": t2["id"]})
    assert res2.status_code == 409
    assert "conflito de horário" in res2.json()["detail"].lower()


def test_regra_2_lista_de_espera_prioridades_e_48_horas(client):
    """
    Regra 2:
    - Se a turma estiver lotada, a matricula entra em lista de espera ordenada pela
      prioridade da categoria (Pós > Graduação > Especial) e, em caso de empate, pela data da solicitacao.
    - Quando uma vaga e liberada, o primeiro da fila tem 48 horas para confirmar;
      esgotado o prazo, a matricula e cancelada e a vez passa ao proximo.
    """
    d = client.post("/disciplinas", json={
        "codigo": "LOT101",
        "nome": "Turma Pequena",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Geral"
    }).json()

    # Turma com apenas 1 vaga!
    t = client.post("/turmas", json={
        "disciplina_id": d["id"],
        "semestre": "2026.1",
        "professor": "Prof Vaga Unica",
        "numero_vagas": 1,
        "horario": "SEX 08:00-10:00"
    }).json()

    # Aluno 1: Graduação (ocupará a única vaga)
    aluno_grad1 = client.post("/alunos", json={
        "nome": "Aluno Grad 1",
        "matricula": "G001",
        "email": "g1@univ.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }).json()

    mat_grad1 = client.post("/matriculas", json={"aluno_id": aluno_grad1["id"], "turma_id": t["id"]}).json()
    assert mat_grad1["estado"] == "confirmada"

    # Turma agora está lotada!
    # Criar 3 alunos para a lista de espera em ordem proposital:
    # 1. Aluno Graduação 2
    # 2. Aluno Especial (Baixa prioridade)
    # 3. Aluno Pós (Alta prioridade - solicitou por último, mas tem prioridade mais alta!)
    aluno_grad2 = client.post("/alunos", json={
        "nome": "Aluno Grad 2",
        "matricula": "G002",
        "email": "g2@univ.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }).json()

    aluno_esp = client.post("/alunos", json={
        "nome": "Aluno Especial Fila",
        "matricula": "E001",
        "email": "e1@univ.br",
        "categoria": "especial",
        "situacao": "ativo"
    }).json()

    aluno_pos = client.post("/alunos", json={
        "nome": "Aluno Pos Fila",
        "matricula": "P001",
        "email": "p1@univ.br",
        "categoria": "pos",
        "situacao": "ativo"
    }).json()

    # Solicitações para a fila
    mat_g2 = client.post("/matriculas", json={"aluno_id": aluno_grad2["id"], "turma_id": t["id"]}).json()
    assert mat_g2["estado"] == "lista_de_espera"

    mat_esp = client.post("/matriculas", json={"aluno_id": aluno_esp["id"], "turma_id": t["id"]}).json()
    assert mat_esp["estado"] == "lista_de_espera"

    mat_pos = client.post("/matriculas", json={"aluno_id": aluno_pos["id"], "turma_id": t["id"]}).json()
    assert mat_pos["estado"] == "lista_de_espera"

    # Consultar fila:
    # A ordem DEVE SER: Pós (1º), Grad 2 (2º), Especial (3º)
    fila_res = client.get(f"/turmas/{t['id']}/fila").json()
    assert fila_res["total_na_fila"] == 3
    assert fila_res["fila"][0]["aluno_categoria"] == "pos"
    assert fila_res["fila"][1]["aluno_categoria"] == "graduacao"
    assert fila_res["fila"][2]["aluno_categoria"] == "especial"

    # Agora aluno 1 cancela sua matrícula, liberando a vaga!
    client.post(f"/matriculas/{mat_grad1['id']}/cancelar")

    # A vaga liberada deve passar para o primeiro da fila (Aluno Pós)!
    # Seu estado deve mudar para SOLICITADA e ter data_oferta_vaga preenchida
    fila_atualizada = client.get(f"/turmas/{t['id']}/fila").json()
    primeiro = fila_atualizada["fila"][0]
    assert primeiro["aluno_categoria"] == "pos"
    assert primeiro["estado"] == "solicitada"
    assert primeiro["data_oferta_vaga"] is not None
    assert primeiro["horas_restantes"] <= 48.0

    # Testar expiração das 48 horas: se passar de 48 horas (ex: 49 horas simuladas):
    # O aluno de pós deve ter sua matrícula cancelada e a vaga deve ir para o próximo (Graduação 2)!
    agora_mais_49h = (datetime.now(timezone.utc) + timedelta(hours=49)).isoformat()
    # Tentativa do aluno pós confirmar após 49 horas -> cancela por prazo expirado
    res_pos_tarde = client.post(
        f"/matriculas/{mat_pos['id']}/confirmar",
        json={"data_acao": agora_mais_49h}
    )
    assert res_pos_tarde.status_code == 400
    assert "expirou" in res_pos_tarde.json()["detail"].lower()

    # Verificar que mat_pos agora está CANCELADA
    mat_pos_check = client.get(f"/matriculas/{mat_pos['id']}").json()
    assert mat_pos_check["estado"] == "cancelada"

    # E a vaga agora deve estar ofertada ao Aluno Grad 2!
    mat_g2_check = client.get(f"/matriculas/{mat_g2['id']}").json()
    assert mat_g2_check["estado"] == "solicitada"
    assert mat_g2_check["data_oferta_vaga"] is not None

    # Aluno Grad 2 confirma dentro do prazo (ex: 10 horas após a oferta)
    agora_mais_59h = (datetime.now(timezone.utc) + timedelta(hours=59)).isoformat()
    res_g2_confirma = client.post(
        f"/matriculas/{mat_g2['id']}/confirmar",
        json={"data_acao": agora_mais_59h}
    )
    assert res_g2_confirma.status_code == 200
    assert res_g2_confirma.json()["estado"] == "confirmada"


def test_regra_4_trancamento_e_cancelamento_prazos(client):
    """
    Regra 4:
    - O trancamento de uma disciplina so e permitido dentro do prazo de cancelamento da categoria
      e respeitando o limite de trancamentos.
    - Fora do prazo, o cancelamento registra reprovacao por falta no historico.
    Prazos:
      Graduação: 15 dias, até 2 trancamentos
      Pós: 30 dias, até 1 trancamento
      Especial: 7 dias, 0 trancamentos
    """
    d = client.post("/disciplinas", json={
        "codigo": "PRAZO1",
        "nome": "Disciplina Prazos",
        "numero_creditos": 4,
        "carga_horaria": 60,
        "departamento": "Geral"
    }).json()

    t = client.post("/turmas", json={
        "disciplina_id": d["id"],
        "semestre": "2026.1",
        "professor": "Prof Prazo",
        "numero_vagas": 10,
        "horario": "SEG 10:00-12:00"
    }).json()

    aluno_grad = client.post("/alunos", json={
        "nome": "Aluno Grad Prazo",
        "matricula": "GP001",
        "email": "gp@univ.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }).json()

    aluno_esp = client.post("/alunos", json={
        "nome": "Aluno Esp Prazo",
        "matricula": "EP001",
        "email": "ep@univ.br",
        "categoria": "especial",
        "situacao": "ativo"
    }).json()

    # 1. Aluno especial tenta trancar (limite é 0 trancamentos)
    mat_esp = client.post("/matriculas", json={"aluno_id": aluno_esp["id"], "turma_id": t["id"]}).json()
    res_esp_trancar = client.post(f"/matriculas/{mat_esp['id']}/trancar")
    assert res_esp_trancar.status_code == 400
    assert "especial" in res_esp_trancar.json()["detail"].lower()

    # 2. Aluno graduação tranca dentro do prazo (ex: 5 dias após matrícula)
    mat_grad = client.post("/matriculas", json={"aluno_id": aluno_grad["id"], "turma_id": t["id"]}).json()
    data_5d = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    res_tranc_ok = client.post(
        f"/matriculas/{mat_grad['id']}/trancar",
        json={"data_acao": data_5d}
    )
    assert res_tranc_ok.status_code == 200
    assert res_tranc_ok.json()["estado"] == "trancada"

    # Verificar que no histórico consta TRANCADO
    hist = client.get(f"/alunos/{aluno_grad['id']}/historico").json()
    assert len(hist) == 1
    assert hist[0]["situacao"] == "trancado"

    # 3. Testar cancelamento fora do prazo (Graduação tem 15 dias; cancelar aos 20 dias)
    # Deve registrar REPROVADO_POR_FALTA no histórico
    mat_grad_2 = client.post("/matriculas", json={"aluno_id": aluno_grad["id"], "turma_id": t["id"]}).json()
    data_20d = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()
    res_canc_fora = client.post(
        f"/matriculas/{mat_grad_2['id']}/cancelar",
        json={"data_acao": data_20d}
    )
    assert res_canc_fora.status_code == 200
    assert res_canc_fora.json()["estado"] == "cancelada"

    hist_atualizado = client.get(f"/alunos/{aluno_grad['id']}/historico").json()
    reprovados_falta = [h for h in hist_atualizado if h["situacao"] == "reprovado_por_falta"]
    assert len(reprovados_falta) == 1


    # 4. Testar tentativa de trancar fora do prazo (Graduação: 16 dias > 15 dias)
    mat_grad_3 = client.post("/matriculas", json={"aluno_id": aluno_grad["id"], "turma_id": t["id"]}).json()
    data_16d = (datetime.now(timezone.utc) + timedelta(days=16)).isoformat()
    res_tranc_fora = client.post(
        f"/matriculas/{mat_grad_3['id']}/trancar",
        json={"data_acao": data_16d}
    )
    assert res_tranc_fora.status_code == 400
    assert "expirado" in res_tranc_fora.json()["detail"].lower()


def test_regra_7_tres_trancamentos_semestre_tranca_aluno_e_cancela_matriculas(client):
    """
    Regra 7: Aluno que acumular tres trancamentos no semestre passa a situacao trancado,
    e todas as suas matriculas confirmadas sao canceladas.
    """
    aluno = client.post("/alunos", json={
        "nome": "Aluno Trancamentos",
        "matricula": "TR701",
        "email": "tr7@univ.br",
        "categoria": "graduacao",
        "situacao": "ativo"
    }).json()

    # Criar 4 disciplinas e 4 turmas no mesmo semestre em horários distintos
    turmas = []
    dias = ["SEG", "TER", "QUA", "QUI"]
    for i, dia in enumerate(dias, start=1):
        disc = client.post("/disciplinas", json={
            "codigo": f"DISC{i}",
            "nome": f"Disciplina {i}",
            "numero_creditos": 4,
            "carga_horaria": 60,
            "departamento": "Geral"
        }).json()

        turma = client.post("/turmas", json={
            "disciplina_id": disc["id"],
            "semestre": "2026.1",
            "professor": f"Prof {i}",
            "numero_vagas": 10,
            "horario": f"{dia} 08:00-10:00"
        }).json()
        turmas.append(turma)

    # Matricular nas 4 turmas (16 créditos <= 28)
    matriculas = []
    for t in turmas:
        mat = client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": t["id"]}).json()
        assert mat["estado"] == "confirmada"
        matriculas.append(mat)

    # Trancar a 1ª disciplina -> aluno continua ativo
    client.post(f"/matriculas/{matriculas[0]['id']}/trancar")
    aluno_check1 = client.get(f"/alunos/{aluno['id']}").json()
    assert aluno_check1["situacao"] == "ativo"

    # Trancar a 2ª disciplina -> aluno continua ativo
    client.post(f"/matriculas/{matriculas[1]['id']}/trancar")
    aluno_check2 = client.get(f"/alunos/{aluno['id']}").json()
    assert aluno_check2["situacao"] == "ativo"

    # Trancar a 3ª disciplina -> ATINGIU 3 TRANCAMENTOS NO SEMESTRE!
    client.post(f"/matriculas/{matriculas[2]['id']}/trancar")

    # Aluno agora DEVE estar com situacao "trancado"
    aluno_check3 = client.get(f"/alunos/{aluno['id']}").json()
    assert aluno_check3["situacao"] == "trancado"

    # E a 4ª matrícula (que estava confirmada) DEVE ter sido cancelada!
    mat4_check = client.get(f"/matriculas/{matriculas[3]['id']}").json()
    assert mat4_check["estado"] == "cancelada"
