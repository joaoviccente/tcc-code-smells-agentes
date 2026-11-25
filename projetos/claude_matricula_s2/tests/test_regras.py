import pytest


# ---------------------------------------------------------------- Regra 1
def test_aluno_inativo_nao_matricula(api):
    for situacao in ("trancado", "jubilado"):
        a = api.aluno(situacao=situacao)
        assert api.solicitar(a, api.turma()).status_code == 422


def test_pre_requisito(client, api):
    calc1, calc2 = api.disciplina(), api.disciplina()
    client.post(f"/disciplinas/{calc2['id']}/pre-requisitos", json={"requisito_id": calc1["id"]})
    t = api.turma(calc2)
    a = api.aluno()
    r = api.solicitar(a, t)
    assert r.status_code == 422 and calc1["codigo"] in r.json()["detail"]
    api.historico(a, calc1, "reprovado", 3.0)
    assert api.solicitar(a, t).status_code == 422
    api.historico(a, calc1, "aprovado", 7.5)
    r = api.solicitar(a, t)
    assert r.status_code == 201 and r.json()["estado"] == "solicitada"


@pytest.mark.parametrize("categoria,limite", [("graduacao", 28), ("pos", 16), ("especial", 8)])
def test_limite_de_creditos(api, categoria, limite):
    a = api.aluno(categoria)
    for _ in range(limite // 4):
        assert api.solicitar(a, api.turma(api.disciplina(creditos=4))).status_code == 201
    r = api.solicitar(a, api.turma(api.disciplina(creditos=1)))
    assert r.status_code == 422 and str(limite) in r.json()["detail"]
    # outro semestre nao conta
    assert api.solicitar(a, api.turma(api.disciplina(creditos=4), semestre="2026.2")).status_code == 201


def test_matricula_duplicada(api):
    a, t = api.aluno(), api.turma()
    assert api.solicitar(a, t).status_code == 201
    assert api.solicitar(a, t).status_code == 409


# ---------------------------------------------------------------- Regra 2
def test_lista_de_espera_prioridade_e_prazo_48h(client, api, relogio):
    t = api.turma(vagas=1)
    ocupante = api.aluno("graduacao")
    m0 = api.matricular(ocupante, t)
    assert client.get(f"/turmas/{t['id']}").json()["estado"] == "lotada"

    esp = api.aluno("especial")
    r = api.solicitar(esp, t); relogio.avancar(minutes=1)
    assert r.json()["estado"] == "lista_de_espera"
    grad = api.aluno("graduacao"); m_grad = api.solicitar(grad, t).json(); relogio.avancar(minutes=1)
    pos = api.aluno("pos"); m_pos = api.solicitar(pos, t).json(); relogio.avancar(minutes=1)
    grad2 = api.aluno("graduacao"); api.solicitar(grad2, t)

    fila = client.get(f"/turmas/{t['id']}/lista-espera").json()["fila"]
    assert [f["aluno_id"] for f in fila] == [pos["id"], grad["id"], grad2["id"], esp["id"]]
    assert [f["prioridade"] for f in fila] == ["alta", "media", "media", "baixa"]
    assert client.get(f"/matriculas/{m_pos['id']}").json()["posicao_fila"] == 1

    # sem vaga oferecida nao confirma
    assert client.post(f"/matriculas/{m_pos['id']}/confirmar").status_code == 409

    # vaga liberada -> primeiro da fila (pos) recebe oferta de 48h
    client.post(f"/matriculas/{m0['id']}/cancelar")
    fila = client.get(f"/turmas/{t['id']}/lista-espera").json()["fila"]
    assert fila[0]["aluno_id"] == pos["id"] and fila[0]["vaga_oferecida"]
    assert not fila[1]["vaga_oferecida"]

    # esgota 48h -> pos cancelado, vez passa ao graduando
    relogio.avancar(hours=48, seconds=1)
    m = client.get(f"/matriculas/{m_pos['id']}").json()
    assert m["estado"] == "cancelada"
    assert client.post(f"/matriculas/{m_pos['id']}/confirmar").status_code == 409
    fila = client.get(f"/turmas/{t['id']}/lista-espera").json()["fila"]
    assert fila[0]["aluno_id"] == grad["id"] and fila[0]["vaga_oferecida"]

    relogio.avancar(hours=47)
    r = client.post(f"/matriculas/{m_grad['id']}/confirmar")
    assert r.status_code == 200 and r.json()["estado"] == "confirmada"
    assert client.get(f"/turmas/{t['id']}").json()["estado"] == "lotada"


def test_processamento_em_lote_de_expiracoes(client, api, relogio):
    t = api.turma(vagas=1)
    m0 = api.matricular(api.aluno(), t)
    api.solicitar(api.aluno(), t)
    client.post(f"/matriculas/{m0['id']}/cancelar")
    relogio.avancar(hours=49)
    assert client.post("/lista-espera/processar-expiracoes").json() == {"matriculas_expiradas": 1}


# ---------------------------------------------------------------- Regra 3
def test_tres_reprovacoes_impedem_matricula(api):
    d = api.disciplina()
    a = api.aluno()
    for s in ("2024.1", "2024.2"):
        api.historico(a, d, "reprovado", 2.0, semestre=s)
    assert api.solicitar(a, api.turma(d)).status_code == 201
    b = api.aluno()
    for s in ("2024.1", "2024.2", "2025.1"):
        api.historico(b, d, "reprovado", 2.0, semestre=s)
    r = api.solicitar(b, api.turma(d))
    assert r.status_code == 422 and "reprovado 3 vezes" in r.json()["detail"]


# ---------------------------------------------------------------- Regra 4
@pytest.mark.parametrize("categoria,prazo", [("graduacao", 15), ("pos", 30)])
def test_trancamento_no_prazo(client, api, relogio, categoria, prazo):
    a = api.aluno(categoria)
    m = api.matricular(a, api.turma())
    relogio.avancar(days=prazo)
    r = client.post(f"/matriculas/{m['id']}/trancar")
    assert r.status_code == 200 and r.json()["matricula"]["estado"] == "trancada"
    hist = client.get(f"/alunos/{a['id']}/historico").json()
    assert hist[-1]["situacao"] == "trancado"


@pytest.mark.parametrize("categoria,prazo", [("graduacao", 15), ("pos", 30), ("especial", 7)])
def test_cancelamento_fora_do_prazo_reprova_por_falta(client, api, relogio, categoria, prazo):
    a = api.aluno(categoria)
    m = api.matricular(a, api.turma())
    relogio.avancar(days=prazo, minutes=1)
    if categoria != "especial":
        assert client.post(f"/matriculas/{m['id']}/trancar").status_code == 422
    r = client.post(f"/matriculas/{m['id']}/cancelar").json()
    assert r["reprovacao_por_falta"] is True and r["matricula"]["estado"] == "cancelada"
    hist = client.get(f"/alunos/{a['id']}/historico").json()
    assert hist[-1]["situacao"] == "reprovado" and hist[-1]["nota"] == 0


def test_cancelamento_no_prazo_nao_reprova(client, api, relogio):
    a = api.aluno("especial")
    m = api.matricular(a, api.turma())
    relogio.avancar(days=7)
    assert client.post(f"/matriculas/{m['id']}/cancelar").json()["reprovacao_por_falta"] is False
    assert client.get(f"/alunos/{a['id']}/historico").json() == []


def test_especial_nao_tranca(client, api):
    m = api.matricular(api.aluno("especial"), api.turma())
    assert client.post(f"/matriculas/{m['id']}/trancar").status_code == 422


@pytest.mark.parametrize("categoria,limite", [("graduacao", 2), ("pos", 1)])
def test_limite_trancamentos_por_disciplina(client, api, categoria, limite):
    a, d = api.aluno(categoria), api.disciplina()
    for i in range(limite):
        api.historico(a, d, "trancado", semestre=f"202{i}.1")
    m = api.matricular(a, api.turma(d))
    r = client.post(f"/matriculas/{m['id']}/trancar")
    assert r.status_code == 422 and "trancamento" in r.json()["detail"]


# ---------------------------------------------------------------- Regra 5
def test_encerramento_do_periodo(client, api):
    t4, t5 = api.turma(), api.turma()
    for _ in range(4):
        api.matricular(api.aluno(), t4)
    for _ in range(5):
        api.matricular(api.aluno(), t5)
    pendente = api.solicitar(api.aluno(), t4).json()
    outra_sem = api.turma(semestre="2026.2")
    r = client.post("/semestres/2026.1/encerrar-periodo-matricula").json()
    assert r["turmas_canceladas"] == [t4["id"]] and r["turmas_mantidas"] == [t5["id"]]
    assert r["matriculas_canceladas"] == 5
    assert client.get(f"/turmas/{t4['id']}").json()["estado"] == "cancelada"
    assert client.get(f"/matriculas/{pendente['id']}").json()["estado"] == "cancelada"
    assert client.get(f"/turmas/{outra_sem['id']}").json()["estado"] == "aberta"
    assert api.solicitar(api.aluno(), t4).status_code == 409


# ---------------------------------------------------------------- Regra 6
def test_conflito_de_horario(client, api):
    a = api.aluno()
    t1 = api.turma(horario=[{"dia": "seg", "inicio": "08:00", "fim": "10:00"}])
    t2 = api.turma(horario=[{"dia": "seg", "inicio": "09:00", "fim": "11:00"}])
    t3 = api.turma(horario=[{"dia": "seg", "inicio": "10:00", "fim": "12:00"}])
    api.matricular(a, t1)
    r = api.solicitar(a, t2)
    assert r.status_code == 409 and "horario" in r.json()["detail"]
    assert api.solicitar(a, t3).status_code == 201


def test_conflito_verificado_na_confirmacao(client, api):
    a = api.aluno()
    t1 = api.turma(horario=[{"dia": "ter", "inicio": "08:00", "fim": "10:00"}])
    t2 = api.turma(horario=[{"dia": "ter", "inicio": "09:00", "fim": "11:00"}])
    m1, m2 = api.solicitar(a, t1).json(), api.solicitar(a, t2).json()
    assert client.post(f"/matriculas/{m1['id']}/confirmar").status_code == 200
    assert client.post(f"/matriculas/{m2['id']}/confirmar").status_code == 409


# ---------------------------------------------------------------- Regra 7
def test_tres_trancamentos_no_semestre_trancam_aluno(client, api):
    a = api.aluno("graduacao")
    ms = [api.matricular(a, api.turma()) for _ in range(4)]
    t_cheia = api.turma(vagas=1)
    m_cheia = api.matricular(a, t_cheia)
    espera = api.solicitar(api.aluno(), t_cheia).json()

    for i in range(2):
        r = client.post(f"/matriculas/{ms[i]['id']}/trancar").json()
        assert r["aluno_trancado"] is False and r["trancamentos_no_semestre"] == i + 1
    r = client.post(f"/matriculas/{ms[2]['id']}/trancar").json()
    assert r["aluno_trancado"] is True and r["trancamentos_no_semestre"] == 3

    assert client.get(f"/alunos/{a['id']}").json()["situacao"] == "trancado"
    estados = {m["id"]: m["estado"] for m in client.get(f"/alunos/{a['id']}/matriculas").json()}
    assert estados[ms[3]["id"]] == "cancelada" and estados[m_cheia["id"]] == "cancelada"
    assert [estados[m["id"]] for m in ms[:3]] == ["trancada"] * 3
    # vaga liberada foi oferecida ao proximo da fila
    assert client.get(f"/matriculas/{espera['id']}").json()["prazo_confirmacao"] is not None
    assert api.solicitar(a, api.turma()).status_code == 422


# ---------------------------------------------------------------- Consultas e relatorios
def test_listagem_e_relatorios(client, api):
    d_pop = api.disciplina(departamento="DCC")
    d_mat = api.disciplina(departamento="DMA")
    t1, t2 = api.turma(d_pop, vagas=10), api.turma(d_mat, vagas=4)
    alunos = [api.aluno() for _ in range(3)]
    for a in alunos:
        api.matricular(a, t1)
    api.matricular(alunos[0], t2)

    lst = client.get(f"/alunos/{alunos[0]['id']}/matriculas", params={"semestre": "2026.1"}).json()
    assert len(lst) == 2
    assert client.get("/alunos/999/matriculas").status_code == 404

    rank = client.get("/relatorios/disciplinas-mais-procuradas", params={"semestre": "2026.1"}).json()
    assert rank[0]["disciplina_id"] == d_pop["id"] and rank[0]["total_solicitacoes"] == 3
    assert client.get("/relatorios/disciplinas-mais-procuradas").status_code == 422

    api.historico(alunos[0], d_mat, "aprovado", 8)
    api.historico(alunos[1], d_mat, "reprovado", 4)
    api.historico(alunos[2], d_mat, "reprovado", 2)
    api.historico(alunos[2], d_mat, "trancado")
    taxa = client.get("/relatorios/taxa-reprovacao").json()
    assert taxa[0]["disciplina_id"] == d_mat["id"] and taxa[0]["taxa_reprovacao"] == round(2 / 3, 4)

    oc = {o["departamento"]: o for o in client.get("/relatorios/ocupacao-turmas",
                                                   params={"semestre": "2026.1"}).json()}
    assert oc["DCC"]["total_confirmadas"] == 3 and oc["DCC"]["taxa_ocupacao"] == 0.3
    assert oc["DMA"]["taxa_ocupacao"] == 0.25
