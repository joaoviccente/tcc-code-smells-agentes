import pytest


def erro(r):
    return r.json().get("erro")


def solicitar(client, aluno, turma):
    return client.post("/matriculas", json={"aluno_id": aluno["id"], "turma_id": turma["id"]})


# ------------------------------------------------------------ Regra 1
@pytest.mark.parametrize("situacao", ["trancado", "jubilado"])
def test_somente_aluno_ativo(client, fab, situacao):
    a = fab.aluno(situacao=situacao)
    r = solicitar(client, a, fab.turma())
    assert r.status_code == 422 and erro(r) == "ALUNO_NAO_ATIVO"


def test_pre_requisitos(client, fab):
    a = fab.aluno()
    req = fab.disciplina()
    d = fab.disciplina()
    client.post(f"/disciplinas/{d['id']}/pre-requisitos", json={"requisito_id": req["id"]})
    t = fab.turma(d)
    r = solicitar(client, a, t)
    assert r.status_code == 422 and erro(r) == "PRE_REQUISITOS_PENDENTES"
    fab.historico(a, req, "reprovado")
    assert erro(solicitar(client, a, t)) == "PRE_REQUISITOS_PENDENTES"
    fab.historico(a, req, "aprovado")
    assert solicitar(client, a, t).status_code == 201


@pytest.mark.parametrize("categoria,maximo", [("graduacao", 28), ("pos", 16), ("especial", 8)])
def test_limite_creditos(client, fab, categoria, maximo):
    a = fab.aluno(categoria)
    # preenche exatamente o maximo com disciplinas de 4 creditos
    for _ in range(maximo // 4):
        fab.matricular(a, fab.turma(fab.disciplina(creditos=4)))
    r = solicitar(client, a, fab.turma(fab.disciplina(creditos=1)))
    assert r.status_code == 422 and erro(r) == "LIMITE_CREDITOS_EXCEDIDO"
    assert r.json()["detalhes"]["maximo"] == maximo


def test_creditos_contam_por_semestre(client, fab):
    a = fab.aluno("especial")
    fab.matricular(a, fab.turma(fab.disciplina(creditos=8)))
    assert solicitar(client, a, fab.turma(fab.disciplina(creditos=8),
                                          semestre="2026.2")).status_code == 201


# ------------------------------------------------------------ Regra 2
def test_lista_espera_prioridade_e_48h(client, fab, relogio):
    t = fab.turma(vagas=1)
    dono = fab.aluno()
    m_dono = fab.matricular(dono, t)
    assert client.get(f"/turmas/{t['id']}").json()["estado"] == "lotada"

    esp = fab.aluno("especial")
    grad = fab.aluno("graduacao")
    relogio.avancar(minutes=1)
    pos1 = fab.aluno("pos")
    m_esp = fab.matricular(esp, t)
    relogio.avancar(minutes=1)
    m_grad = fab.matricular(grad, t)
    relogio.avancar(minutes=1)
    m_pos = fab.matricular(pos1, t)
    assert m_esp["estado"] == "lista_de_espera"
    assert m_pos["posicao_lista_espera"] == 1

    fila = client.get(f"/turmas/{t['id']}/lista-espera").json()["fila"]
    assert [f["matricula_id"] for f in fila] == [m_pos["id"], m_grad["id"], m_esp["id"]]

    # em espera sem vaga oferecida nao pode confirmar
    r = client.post(f"/matriculas/{m_grad['id']}/confirmar")
    assert r.status_code == 409 and erro(r) == "AGUARDANDO_VAGA"

    # vaga liberada -> primeiro (pos) recebe 48h
    client.post(f"/matriculas/{m_dono['id']}/cancelar")
    fila = client.get(f"/turmas/{t['id']}/lista-espera").json()["fila"]
    assert fila[0]["vaga_oferecida"] and fila[0]["matricula_id"] == m_pos["id"]
    assert not fila[1]["vaga_oferecida"]

    # 48h passam -> pos cancelado, vez do graduando
    relogio.avancar(hours=48, seconds=1)
    r = client.post(f"/matriculas/{m_pos['id']}/confirmar")
    assert r.status_code == 409 and erro(r) == "PRAZO_CONFIRMACAO_EXPIRADO"
    assert client.get(f"/matriculas/{m_pos['id']}").json()["estado"] == "cancelada"
    fila = client.get(f"/turmas/{t['id']}/lista-espera").json()["fila"]
    assert fila[0]["matricula_id"] == m_grad["id"] and fila[0]["vaga_oferecida"]

    # graduando confirma dentro do prazo
    relogio.avancar(hours=47)
    r = client.post(f"/matriculas/{m_grad['id']}/confirmar")
    assert r.status_code == 200 and r.json()["estado"] == "confirmada"
    assert client.get(f"/turmas/{t['id']}").json()["estado"] == "lotada"


def test_empate_de_prioridade_por_data(client, fab, relogio):
    t = fab.turma(vagas=1)
    fab.matricular(fab.aluno(), t)
    a1, a2 = fab.aluno(), fab.aluno()
    m2 = fab.matricular(a2, t)
    relogio.avancar(seconds=10)
    m1 = fab.matricular(a1, t)
    fila = client.get(f"/turmas/{t['id']}/lista-espera").json()["fila"]
    assert [f["matricula_id"] for f in fila] == [m2["id"], m1["id"]]


# ------------------------------------------------------------ Regra 3
def test_tres_reprovacoes_impedem(client, fab):
    a, d = fab.aluno(), fab.disciplina()
    t = fab.turma(d)
    fab.historico(a, d, "reprovado", semestre="2024.1")
    fab.historico(a, d, "reprovado", semestre="2024.2")
    assert solicitar(client, a, t).status_code == 201
    a2 = fab.aluno()
    for s in ("2024.1", "2024.2", "2025.1"):
        fab.historico(a2, d, "reprovado", semestre=s)
    r = solicitar(client, a2, t)
    assert r.status_code == 422 and erro(r) == "IMPEDIDO_POR_REPROVACOES"


# ------------------------------------------------------------ Regra 4
@pytest.mark.parametrize("categoria,dias", [("graduacao", 15), ("pos", 30)])
def test_trancamento_no_prazo(client, fab, relogio, categoria, dias):
    a = fab.aluno(categoria)
    m = fab.matricular(a, fab.turma())
    relogio.avancar(days=dias)
    r = client.post(f"/matriculas/{m['id']}/trancar")
    assert r.status_code == 200 and r.json()["matricula"]["estado"] == "trancada"
    hist = client.get(f"/alunos/{a['id']}/historico").json()
    assert hist[-1]["situacao"] == "trancado"


@pytest.mark.parametrize("categoria,dias", [("graduacao", 15), ("pos", 30)])
def test_trancamento_fora_do_prazo(client, fab, relogio, categoria, dias):
    m = fab.matricular(fab.aluno(categoria), fab.turma())
    relogio.avancar(days=dias, seconds=1)
    r = client.post(f"/matriculas/{m['id']}/trancar")
    assert r.status_code == 422 and erro(r) == "PRAZO_TRANCAMENTO_EXPIRADO"


def test_especial_nao_tranca(client, fab):
    m = fab.matricular(fab.aluno("especial"), fab.turma())
    r = client.post(f"/matriculas/{m['id']}/trancar")
    assert r.status_code == 422 and erro(r) == "TRANCAMENTO_NAO_PERMITIDO"


@pytest.mark.parametrize("categoria,limite", [("graduacao", 2), ("pos", 1)])
def test_limite_trancamentos_por_disciplina(client, fab, categoria, limite):
    a, d = fab.aluno(categoria), fab.disciplina()
    for i in range(limite):
        m = fab.matricular(a, fab.turma(d, semestre=f"202{i}.1"))
        assert client.post(f"/matriculas/{m['id']}/trancar").status_code == 200
    m = fab.matricular(a, fab.turma(d, semestre="2029.1"))
    r = client.post(f"/matriculas/{m['id']}/trancar")
    assert r.status_code == 422 and erro(r) == "LIMITE_TRANCAMENTOS_EXCEDIDO"


@pytest.mark.parametrize("categoria,dias", [("graduacao", 15), ("pos", 30), ("especial", 7)])
def test_cancelamento_fora_do_prazo_reprova(client, fab, relogio, categoria, dias):
    a = fab.aluno(categoria)
    m1 = fab.matricular(a, fab.turma())
    m2 = fab.matricular(a, fab.turma())
    relogio.avancar(days=dias)
    r = client.post(f"/matriculas/{m1['id']}/cancelar").json()
    assert r["dentro_do_prazo"] and not r["reprovacao_registrada"]
    relogio.avancar(seconds=1)
    r = client.post(f"/matriculas/{m2['id']}/cancelar").json()
    assert not r["dentro_do_prazo"] and r["reprovacao_registrada"]
    hist = client.get(f"/alunos/{a['id']}/historico").json()
    assert len(hist) == 1 and hist[0]["situacao"] == "reprovado"
    assert "falta" in hist[0]["observacao"]


def test_cancelar_duas_vezes(client, fab):
    m = fab.matricular(fab.aluno(), fab.turma())
    assert client.post(f"/matriculas/{m['id']}/cancelar").status_code == 200
    assert client.post(f"/matriculas/{m['id']}/cancelar").status_code == 409


# ------------------------------------------------------------ Regra 5
def test_encerramento_periodo(client, fab):
    t_ok, t_fraca = fab.turma(), fab.turma()
    for _ in range(5):
        fab.matricular(fab.aluno(), t_ok)
    ms = [fab.matricular(fab.aluno(), t_fraca) for _ in range(4)]
    pend = fab.matricular(fab.aluno(), t_fraca, confirmar=False)
    r = client.post("/semestres/2026.1/encerrar-periodo-matricula")
    assert r.status_code == 200
    body = r.json()
    assert [x["turma_id"] for x in body["turmas_canceladas"]] == [t_fraca["id"]]
    assert [x["turma_id"] for x in body["turmas_mantidas"]] == [t_ok["id"]]
    assert client.get(f"/turmas/{t_fraca['id']}").json()["estado"] == "cancelada"
    for m in ms + [pend]:
        assert client.get(f"/matriculas/{m['id']}").json()["estado"] == "cancelada"


# ------------------------------------------------------------ Regra 6
def test_conflito_horario(client, fab):
    a = fab.aluno()
    h = [{"dia": "seg", "inicio": "08:00", "fim": "10:00"}]
    fab.matricular(a, fab.turma(horario=h))
    r = solicitar(client, a, fab.turma(horario=[{"dia": "seg", "inicio": "09:00", "fim": "11:00"}]))
    assert r.status_code == 422 and erro(r) == "CONFLITO_HORARIO"
    # encostado (10:00) nao conflita
    assert solicitar(client, a, fab.turma(
        horario=[{"dia": "seg", "inicio": "10:00", "fim": "12:00"}])).status_code == 201


def test_conflito_rechecado_na_confirmacao(client, fab):
    a = fab.aluno()
    h = [{"dia": "ter", "inicio": "08:00", "fim": "10:00"}]
    m1 = fab.matricular(a, fab.turma(horario=h), confirmar=False)
    m2 = fab.matricular(a, fab.turma(horario=h), confirmar=False)
    assert client.post(f"/matriculas/{m1['id']}/confirmar").status_code == 200
    r = client.post(f"/matriculas/{m2['id']}/confirmar")
    assert r.status_code == 422 and erro(r) == "CONFLITO_HORARIO"


# ------------------------------------------------------------ Regra 7
def test_tres_trancamentos_trancam_aluno(client, fab):
    a = fab.aluno("graduacao")
    ms = [fab.matricular(a, fab.turma(fab.disciplina(creditos=4))) for _ in range(5)]
    outro_sem = fab.matricular(a, fab.turma(semestre="2026.2"))
    for m in ms[:2]:
        r = client.post(f"/matriculas/{m['id']}/trancar").json()
        assert not r["aluno_trancado"]
    r = client.post(f"/matriculas/{ms[2]['id']}/trancar").json()
    assert r["aluno_trancado"] and r["trancamentos_no_semestre"] == 3
    assert sorted(r["matriculas_canceladas"]) == sorted([ms[3]["id"], ms[4]["id"], outro_sem["id"]])
    assert client.get(f"/alunos/{a['id']}").json()["situacao"] == "trancado"
    assert erro(solicitar(client, a, fab.turma())) == "ALUNO_NAO_ATIVO"


# ------------------------------------------------------------ diversos
def test_matricula_duplicada_e_turma_cancelada(client, fab):
    a, d = fab.aluno(), fab.disciplina()
    t1, t2 = fab.turma(d), fab.turma(d)
    fab.matricular(a, t1)
    assert erro(solicitar(client, a, t2)) == "MATRICULA_DUPLICADA"
    client.patch(f"/turmas/{t2['id']}", json={"estado": "cancelada"})
    r = solicitar(client, fab.aluno(), t2)
    assert r.status_code == 409 and erro(r) == "TURMA_INDISPONIVEL"
    assert solicitar(client, {"id": 999}, t1).status_code == 404


def test_listar_por_aluno_e_relatorios(client, fab):
    a = fab.aluno()
    d1 = fab.disciplina(departamento="MAT")
    d2 = fab.disciplina(departamento="FIS")
    t1 = fab.turma(d1, vagas=2)
    fab.matricular(a, t1)
    fab.matricular(fab.aluno(), t1)
    fab.matricular(fab.aluno(), t1)  # espera
    fab.matricular(fab.aluno(), fab.turma(d2, vagas=4))
    assert len(client.get(f"/alunos/{a['id']}/matriculas").json()) == 1

    proc = client.get("/relatorios/disciplinas-mais-procuradas?semestre=2026.1").json()
    assert proc["disciplinas"][0]["disciplina_id"] == d1["id"]
    assert proc["disciplinas"][0]["total_solicitacoes"] == 3

    fab.historico(a, d1, "aprovado")
    fab.historico(fab.aluno(), d1, "reprovado")
    fab.historico(fab.aluno(), d1, "reprovado")
    fab.historico(fab.aluno(), d1, "trancado")
    tx = client.get("/relatorios/taxa-reprovacao").json()["disciplinas"]
    assert tx[0]["taxa_reprovacao"] == round(2 / 3, 4) and tx[0]["trancados"] == 1

    oc = {d["departamento"]: d for d in
          client.get("/relatorios/ocupacao-turmas?semestre=2026.1").json()["departamentos"]}
    assert oc["MAT"]["ocupacao"] == 1.0 and oc["FIS"]["ocupacao"] == 0.25
