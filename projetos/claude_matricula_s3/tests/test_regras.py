import pytest


def erro(r):
    return r.json()["erro"]["codigo"]


# --------------------------------------------------------------- Regra 1
def test_aluno_nao_ativo_nao_matricula(client, f):
    a = f.aluno(situacao="jubilado")
    t = f.turma()
    r = client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": t["id"]})
    assert r.status_code == 422 and erro(r) == "ALUNO_NAO_ATIVO"


def test_pre_requisitos(client, f):
    calc1, calc2 = f.disciplina(), f.disciplina()
    client.post(f"/disciplinas/{calc2['id']}/pre-requisitos", json={"requisito_id": calc1["id"]})
    t = f.turma(calc2["id"])
    a = f.aluno()
    r = client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": t["id"]})
    assert r.status_code == 422 and erro(r) == "PRE_REQUISITOS_PENDENTES"
    assert r.json()["erro"]["detalhes"]["pendentes"] == [calc1["codigo"]]
    f.historico(a["id"], calc1["id"], "reprovado")
    assert client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": t["id"]}).status_code == 422
    f.historico(a["id"], calc1["id"], "aprovado")
    f.solicitar(a["id"], t["id"])


@pytest.mark.parametrize("categoria,limite", [("graduacao", 28), ("pos", 16), ("especial", 8)])
def test_limite_creditos_por_categoria(client, f, categoria, limite):
    a = f.aluno(categoria)
    usados = 0
    while usados + 4 <= limite:
        f.matricular(a["id"], f.turma(f.disciplina(creditos=4)["id"])["id"])
        usados += 4
    sobra = limite - usados
    if sobra:
        f.matricular(a["id"], f.turma(f.disciplina(creditos=sobra)["id"])["id"])
    # exatamente no limite; mais 1 crédito excede
    t = f.turma(f.disciplina(creditos=1)["id"])
    r = client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": t["id"]})
    assert r.status_code == 422 and erro(r) == "LIMITE_CREDITOS_EXCEDIDO"
    assert r.json()["erro"]["detalhes"]["limite"] == limite


def test_creditos_contam_por_semestre(client, f):
    a = f.aluno("especial")
    f.matricular(a["id"], f.turma(f.disciplina(creditos=8)["id"], semestre="2026.1")["id"])
    f.matricular(a["id"], f.turma(f.disciplina(creditos=8)["id"], semestre="2026.2")["id"])


def test_matricula_duplicada(client, f):
    d = f.disciplina()
    t1, t2 = f.turma(d["id"]), f.turma(d["id"])
    a = f.aluno()
    f.solicitar(a["id"], t1["id"])
    r = client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": t2["id"]})
    assert r.status_code == 409 and erro(r) == "MATRICULA_DUPLICADA"


# --------------------------------------------------------------- Regra 2
def test_lista_de_espera_prioridade_e_prazo_48h(client, f, relogio):
    t = f.turma(vagas=1)
    ocupante = f.aluno()
    m0 = f.matricular(ocupante["id"], t["id"])
    assert client.get(f"/turmas/{t['id']}").json()["estado"] == "lotada"

    esp = f.aluno("especial")
    relogio.avancar(minutes=1)
    grad = f.aluno("graduacao")
    me = f.solicitar(esp["id"], t["id"])["matricula"]
    relogio.avancar(minutes=1)
    mg = f.solicitar(grad["id"], t["id"])["matricula"]
    relogio.avancar(minutes=1)
    pos = f.aluno("pos")
    mp = f.solicitar(pos["id"], t["id"])["matricula"]
    relogio.avancar(minutes=1)
    grad2 = f.aluno("graduacao")
    mg2 = f.solicitar(grad2["id"], t["id"])["matricula"]
    assert me["estado"] == "lista_de_espera"

    fila = client.get(f"/turmas/{t['id']}/lista-espera").json()["fila"]
    assert [i["matricula_id"] for i in fila] == [mp["id"], mg["id"], mg2["id"], me["id"]]
    assert [i["prioridade"] for i in fila] == ["alta", "media", "media", "baixa"]

    # Sem oferta ainda, não pode confirmar
    r = client.post(f"/matriculas/{mp['id']}/confirmar")
    assert r.status_code == 409 and erro(r) == "AGUARDANDO_VAGA"

    # Vaga liberada => primeiro da fila recebe prazo de 48h
    assert client.post(f"/matriculas/{m0['id']}/cancelar").status_code == 200
    fila = client.get(f"/turmas/{t['id']}/lista-espera").json()["fila"]
    assert fila[0]["matricula_id"] == mp["id"] and fila[0]["vaga_ofertada"]
    assert fila[0]["prazo_confirmacao"] == "2026-02-03T10:04:00Z"
    assert not fila[1]["vaga_ofertada"]

    # Nova solicitação continua indo para a fila (vaga reservada)
    outro = f.aluno("pos")
    assert f.solicitar(outro["id"], t["id"])["matricula"]["estado"] == "lista_de_espera"

    # Prazo de 48h esgotado => cancela e passa ao próximo (o outro "pos")
    relogio.avancar(hours=48, minutes=1)
    m = client.get(f"/matriculas/{mp['id']}").json()
    assert m["estado"] == "cancelada"
    fila = client.get(f"/turmas/{t['id']}/lista-espera").json()["fila"]
    assert fila[0]["aluno_id"] == outro["id"] and fila[0]["vaga_ofertada"]

    # Próximo confirma dentro do prazo
    relogio.avancar(hours=47)
    r = client.post(f"/matriculas/{fila[0]['matricula_id']}/confirmar")
    assert r.status_code == 200 and r.json()["matricula"]["estado"] == "confirmada"
    assert client.get(f"/turmas/{t['id']}").json()["estado"] == "lotada"


def test_oferta_exatamente_48h_ainda_valida(client, f, relogio):
    t = f.turma(vagas=1)
    m0 = f.matricular(f.aluno()["id"], t["id"])
    mw = f.solicitar(f.aluno()["id"], t["id"])["matricula"]
    client.post(f"/matriculas/{m0['id']}/cancelar")
    relogio.avancar(hours=48)
    assert client.post(f"/matriculas/{mw['id']}/confirmar").status_code == 200


# --------------------------------------------------------------- Regra 3
def test_tres_reprovacoes_impedem_matricula(client, f):
    d = f.disciplina()
    t = f.turma(d["id"])
    a = f.aluno()
    f.historico(a["id"], d["id"], "reprovado", semestre="2024.1")
    f.historico(a["id"], d["id"], "reprovado", semestre="2024.2")
    m = f.solicitar(a["id"], t["id"])["matricula"]
    client.post(f"/matriculas/{m['id']}/cancelar")
    f.historico(a["id"], d["id"], "reprovado", semestre="2025.1")
    r = client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": t["id"]})
    assert r.status_code == 422 and erro(r) == "LIMITE_REPROVACOES"


# --------------------------------------------------------------- Regra 4
@pytest.mark.parametrize("categoria,prazo", [("graduacao", 15), ("pos", 30), ("especial", 7)])
def test_cancelamento_dentro_e_fora_do_prazo(client, f, relogio, categoria, prazo):
    a = f.aluno(categoria)
    m1 = f.matricular(a["id"], f.turma(f.disciplina(creditos=2)["id"])["id"])
    m2 = f.matricular(a["id"], f.turma(f.disciplina(creditos=2)["id"])["id"])
    relogio.avancar(days=prazo)
    r = client.post(f"/matriculas/{m1['id']}/cancelar")
    assert r.status_code == 200 and not r.json()["reprovacao_por_falta_registrada"]
    relogio.avancar(seconds=1)
    r = client.post(f"/matriculas/{m2['id']}/cancelar")
    assert r.status_code == 200 and r.json()["reprovacao_por_falta_registrada"]
    hist = client.get(f"/alunos/{a['id']}/historico").json()
    assert len(hist) == 1 and hist[0]["situacao"] == "reprovado" and hist[0]["nota"] == 0


def test_trancamento_prazo_e_limites(client, f, relogio):
    # graduacao: 2 trancamentos por disciplina
    a = f.aluno("graduacao")
    d = f.disciplina()
    for sem in ("2026.1", "2026.2"):
        m = f.matricular(a["id"], f.turma(d["id"], semestre=sem)["id"])
        r = client.post(f"/matriculas/{m['id']}/trancar")
        assert r.status_code == 200 and r.json()["matricula"]["estado"] == "trancada"
    m = f.matricular(a["id"], f.turma(d["id"], semestre="2027.1")["id"])
    r = client.post(f"/matriculas/{m['id']}/trancar")
    assert r.status_code == 422 and erro(r) == "LIMITE_TRANCAMENTOS_DISCIPLINA"

    # pos: 1 trancamento por disciplina
    p = f.aluno("pos")
    d2 = f.disciplina()
    m = f.matricular(p["id"], f.turma(d2["id"], semestre="2026.1")["id"])
    assert client.post(f"/matriculas/{m['id']}/trancar").status_code == 200
    m = f.matricular(p["id"], f.turma(d2["id"], semestre="2026.2")["id"])
    assert erro(client.post(f"/matriculas/{m['id']}/trancar")) == "LIMITE_TRANCAMENTOS_DISCIPLINA"

    # especial: nenhum trancamento
    e = f.aluno("especial")
    m = f.matricular(e["id"], f.turma()["id"])
    r = client.post(f"/matriculas/{m['id']}/trancar")
    assert r.status_code == 422 and erro(r) == "TRANCAMENTO_NAO_PERMITIDO"

    # fora do prazo (graduacao 15 dias)
    g = f.aluno("graduacao")
    m = f.matricular(g["id"], f.turma()["id"])
    relogio.avancar(days=15, seconds=1)
    r = client.post(f"/matriculas/{m['id']}/trancar")
    assert r.status_code == 422 and erro(r) == "PRAZO_TRANCAMENTO_EXPIRADO"


def test_trancamento_libera_vaga_para_fila(client, f):
    t = f.turma(vagas=1)
    m0 = f.matricular(f.aluno()["id"], t["id"])
    mw = f.solicitar(f.aluno()["id"], t["id"])["matricula"]
    client.post(f"/matriculas/{m0['id']}/trancar")
    assert client.post(f"/matriculas/{mw['id']}/confirmar").status_code == 200


# --------------------------------------------------------------- Regra 5
def test_encerramento_periodo_cancela_turmas_com_menos_de_5(client, f):
    t4, t5 = f.turma(), f.turma()
    for _ in range(4):
        f.matricular(f.aluno()["id"], t4["id"])
    pendente = f.solicitar(f.aluno()["id"], t4["id"])["matricula"]  # não confirmada
    for _ in range(5):
        f.matricular(f.aluno()["id"], t5["id"])
    r = client.post("/periodos/2026.1/encerrar-matriculas")
    assert r.status_code == 200
    assert r.json()["turmas_canceladas"] == [t4["id"]]
    assert r.json()["turmas_mantidas"] == [t5["id"]]
    assert r.json()["matriculas_canceladas"] == 5
    assert client.get(f"/turmas/{t4['id']}").json()["estado"] == "cancelada"
    assert client.get(f"/matriculas/{pendente['id']}").json()["estado"] == "cancelada"
    assert client.post("/periodos/2026.1/encerrar-matriculas").status_code == 409
    r = client.post("/matriculas", json={"aluno_id": f.aluno()["id"], "turma_id": t5["id"]})
    assert r.status_code == 409 and erro(r) == "PERIODO_MATRICULA_ENCERRADO"


# --------------------------------------------------------------- Regra 6
def test_conflito_de_horario(client, f):
    a = f.aluno()
    h = [{"dia": "TER", "inicio": "08:00", "fim": "10:00"}]
    t1 = f.turma(horarios=h)
    t2 = f.turma(horarios=[{"dia": "TER", "inicio": "09:30", "fim": "11:00"}])
    t3 = f.turma(horarios=[{"dia": "TER", "inicio": "10:00", "fim": "12:00"}])  # encosta, não conflita
    f.matricular(a["id"], t1["id"])
    r = client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": t2["id"]})
    assert r.status_code == 422 and erro(r) == "CONFLITO_HORARIO"
    f.matricular(a["id"], t3["id"])


def test_conflito_verificado_na_confirmacao(client, f):
    a = f.aluno()
    h = [{"dia": "QUA", "inicio": "14:00", "fim": "16:00"}]
    m1 = f.solicitar(a["id"], f.turma(horarios=h)["id"])["matricula"]
    m2 = f.solicitar(a["id"], f.turma(horarios=h)["id"])["matricula"]
    assert client.post(f"/matriculas/{m1['id']}/confirmar").status_code == 200
    r = client.post(f"/matriculas/{m2['id']}/confirmar")
    assert r.status_code == 422 and erro(r) == "CONFLITO_HORARIO"


# --------------------------------------------------------------- Regra 7
def test_tres_trancamentos_no_semestre_trancam_aluno(client, f):
    a = f.aluno("graduacao")
    ms = [f.matricular(a["id"], f.turma(f.disciplina(creditos=4)["id"])["id"]) for _ in range(5)]
    for m in ms[:2]:
        r = client.post(f"/matriculas/{m['id']}/trancar")
        assert r.status_code == 200 and not r.json()["aluno_trancado"]
    r = client.post(f"/matriculas/{ms[2]['id']}/trancar")
    assert r.status_code == 200 and r.json()["aluno_trancado"]
    assert sorted(r.json()["matriculas_canceladas"]) == sorted([ms[3]["id"], ms[4]["id"]])
    assert client.get(f"/alunos/{a['id']}").json()["situacao"] == "trancado"
    estados = {m["id"]: m["estado"] for m in client.get(f"/alunos/{a['id']}/matriculas").json()}
    assert [estados[m["id"]] for m in ms] == ["trancada"] * 3 + ["cancelada"] * 2
    r = client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": f.turma()["id"]})
    assert r.status_code == 422 and erro(r) == "ALUNO_NAO_ATIVO"


# ------------------------------------------------------------ Relatórios
def test_relatorios(client, f):
    d1 = f.disciplina(departamento="DMAT")
    d2 = f.disciplina(departamento="DCOMP")
    t1, t2 = f.turma(d1["id"], vagas=10), f.turma(d2["id"], vagas=4)
    for _ in range(3):
        f.matricular(f.aluno()["id"], t1["id"])
    f.matricular(f.aluno()["id"], t2["id"])
    r = client.get("/relatorios/disciplinas-mais-procuradas", params={"semestre": "2026.1"}).json()
    assert [d["codigo"] for d in r["disciplinas"]] == [d1["codigo"], d2["codigo"]]
    assert r["disciplinas"][0]["total_solicitacoes"] == 3

    a = f.aluno()
    f.historico(a["id"], d1["id"], "reprovado")
    f.historico(f.aluno()["id"], d1["id"], "aprovado")
    f.historico(f.aluno()["id"], d1["id"], "aprovado")
    f.historico(f.aluno()["id"], d1["id"], "reprovado")
    r = client.get("/relatorios/taxa-reprovacao").json()
    assert r["disciplinas"][0]["taxa_reprovacao"] == 0.5

    r = client.get("/relatorios/ocupacao-turmas", params={"semestre": "2026.1"}).json()
    deps = {d["departamento"]: d for d in r["departamentos"]}
    assert deps["DMAT"]["taxa_ocupacao"] == 0.3
    assert deps["DCOMP"]["taxa_ocupacao"] == 0.25
    assert client.get("/relatorios/ocupacao-turmas", params={"semestre": "26"}).status_code == 422
