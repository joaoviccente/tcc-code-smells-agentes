from datetime import timedelta

import pytest

from app import clock

HORARIOS = [("SEG", "08:00", "10:00"), ("TER", "08:00", "10:00"), ("QUA", "08:00", "10:00"),
            ("QUI", "08:00", "10:00"), ("SEX", "08:00", "10:00"), ("SEG", "10:00", "12:00"),
            ("TER", "10:00", "12:00"), ("QUA", "10:00", "12:00"), ("QUI", "10:00", "12:00")]


def _turmas(api, n, creditos=4):
    return [api.turma(api.disciplina(creditos=creditos), dia=d, inicio=i, fim=f) for d, i, f in HORARIOS[:n]]


# ------------------------------------------------------------------ CRUD / validacao
def test_crud_aluno_e_validacao(client, api):
    aid = api.aluno()
    assert client.get(f"/alunos/{aid}").json()["situacao"] == "ativo"
    assert client.post("/alunos", json={"nome": "X", "matricula": "A00001", "email": "z@uni.br",
                                        "categoria": "pos"}).status_code == 409
    assert client.post("/alunos", json={"nome": "X", "matricula": "B1234", "email": "invalido",
                                        "categoria": "pos"}).status_code == 422
    assert client.post("/alunos", json={"nome": "X", "matricula": "B1234", "email": "a@b.br",
                                        "categoria": "doutorado"}).status_code == 422
    assert client.patch(f"/alunos/{aid}", json={"nome": "Novo"}).json()["nome"] == "Novo"
    assert client.get("/alunos/999").status_code == 404
    assert client.delete(f"/alunos/{aid}").status_code == 204


def test_crud_turma_validacao(client, api):
    d = api.disciplina()
    base = {"disciplina_id": d, "semestre": "2026.2", "professor": "P", "vagas": 10,
            "horarios": [{"dia_semana": "SEG", "hora_inicio": "10:00", "hora_fim": "08:00"}]}
    assert client.post("/turmas", json=base).status_code == 422
    base["horarios"][0] = {"dia_semana": "SEG", "hora_inicio": "08:00", "hora_fim": "10:00"}
    assert client.post("/turmas", json={**base, "vagas": 0}).status_code == 422
    assert client.post("/turmas", json={**base, "semestre": "2026-2"}).status_code == 422
    assert client.post("/turmas", json={**base, "disciplina_id": 999}).status_code == 404
    r = client.post("/turmas", json=base)
    assert r.status_code == 201 and r.json()["estado"] == "aberta"


def test_pre_requisito_ciclico(client, api):
    a = api.disciplina()
    b = api.disciplina(pre=[a])
    r = client.post(f"/disciplinas/{a}/pre-requisitos", json={"requisito_id": b})
    assert r.status_code == 422


# ---------------------------------------------------------------------- Regra 1
def test_regra1_aluno_inativo(client, api):
    aid = api.aluno(situacao="jubilado")
    t = api.turma(api.disciplina())
    r = api.solicitar(aid, t)
    assert r.status_code == 403 and r.json()["erro"] == "aluno_inativo"


def test_regra1_pre_requisitos(client, api):
    aid = api.aluno()
    calc1 = api.disciplina()
    calc2 = api.disciplina(pre=[calc1])
    t = api.turma(calc2)
    r = api.solicitar(aid, t)
    assert r.status_code == 422 and r.json()["erro"] == "pre_requisitos_pendentes"
    api.historico(aid, calc1, "reprovado", 3.0)
    assert api.solicitar(aid, t).status_code == 422
    api.historico(aid, calc1, "aprovado", 7.5)
    assert api.solicitar(aid, t).status_code == 201


@pytest.mark.parametrize("categoria,limite", [("graduacao", 28), ("pos", 16), ("especial", 8)])
def test_regra1_limite_creditos(client, api, categoria, limite):
    aid = api.aluno(categoria)
    turmas = _turmas(api, limite // 4 + 1, creditos=4)
    for t in turmas[:-1]:
        assert api.solicitar(aid, t).status_code == 201
    r = api.solicitar(aid, turmas[-1])
    assert r.status_code == 422 and r.json()["erro"] == "limite_creditos_excedido"
    assert r.json()["detalhes"]["limite"] == limite


# ---------------------------------------------------------------------- Regra 2
def test_regra2_lista_espera_prioridade_e_48h(client, api):
    t = api.turma(api.disciplina(), vagas=1)
    ocupante = api.aluno()
    m0 = api.matricular(ocupante, t)
    assert client.get(f"/turmas/{t}").json()["estado"] == "lotada"

    esp = api.aluno("especial")
    grad = api.aluno("graduacao")
    pos1 = api.aluno("pos")
    clock.avancar(timedelta(minutes=1))
    pos2 = api.aluno("pos")
    ids = {}
    for a in (esp, grad, pos1):
        r = api.solicitar(a, t)
        assert r.status_code == 201 and r.json()["estado"] == "lista_de_espera"
        ids[a] = r.json()["id"]
    clock.avancar(timedelta(minutes=1))
    ids[pos2] = api.solicitar(pos2, t).json()["id"]

    fila = client.get(f"/turmas/{t}/lista-espera").json()["fila"]
    assert [i["aluno_id"] for i in fila] == [pos1, pos2, grad, esp]
    assert [i["prioridade"] for i in fila] == ["alta", "alta", "media", "baixa"]

    # confirmar estando na fila -> 409
    assert client.post(f"/matriculas/{ids[pos1]}/confirmar").status_code == 409

    # vaga liberada -> primeiro da fila tem 48h
    assert client.post(f"/matriculas/{m0}/cancelar").status_code == 200
    m = client.get(f"/matriculas/{ids[pos1]}").json()
    assert m["estado"] == "solicitada" and m["prazo_confirmacao"] is not None

    # esgotado o prazo: cancelada e a vez passa ao proximo
    clock.avancar(timedelta(hours=48, seconds=1))
    assert client.get(f"/matriculas/{ids[pos1]}").json()["estado"] == "cancelada"
    assert client.post(f"/matriculas/{ids[pos1]}/confirmar").status_code == 409
    assert client.get(f"/matriculas/{ids[pos2]}").json()["estado"] == "solicitada"

    # proximo confirma dentro do prazo
    clock.avancar(timedelta(hours=47))
    r = client.post(f"/matriculas/{ids[pos2]}/confirmar")
    assert r.status_code == 200 and r.json()["estado"] == "confirmada"
    assert [i["aluno_id"] for i in client.get(f"/turmas/{t}/lista-espera").json()["fila"]] == [grad, esp]


def test_regra2_expiracoes_em_cadeia(client, api):
    t = api.turma(api.disciplina(), vagas=1)
    m0 = api.matricular(api.aluno(), t)
    a, b = api.aluno(), api.aluno()
    ma = api.solicitar(a, t).json()["id"]
    mb = api.solicitar(b, t).json()["id"]
    client.post(f"/matriculas/{m0}/cancelar")
    clock.avancar(timedelta(hours=97))  # ambos os prazos de 48h esgotados
    assert client.get(f"/matriculas/{ma}").json()["estado"] == "cancelada"
    assert client.get(f"/matriculas/{mb}").json()["estado"] == "cancelada"
    assert client.get(f"/turmas/{t}").json()["estado"] == "aberta"


# ---------------------------------------------------------------------- Regra 3
def test_regra3_tres_reprovacoes(client, api):
    aid = api.aluno()
    d = api.disciplina()
    t = api.turma(d)
    for _ in range(2):
        api.historico(aid, d, "reprovado", 2.0)
    r = api.solicitar(aid, t)
    assert r.status_code == 201
    client.post(f"/matriculas/{r.json()['id']}/cancelar")
    api.historico(aid, d, "reprovado", 2.0)
    r = api.solicitar(aid, t)
    assert r.status_code == 403 and r.json()["erro"] == "aluno_impedido_reprovacoes"


# ---------------------------------------------------------------------- Regra 4
@pytest.mark.parametrize("categoria,prazo", [("graduacao", 15), ("pos", 30), ("especial", 7)])
def test_regra4_cancelamento_fora_do_prazo_reprova(client, api, categoria, prazo):
    aid = api.aluno(categoria)
    t = api.turma(api.disciplina())
    m = api.matricular(aid, t)
    clock.avancar(timedelta(days=prazo, seconds=1))
    assert client.post(f"/matriculas/{m}/trancar").status_code == 422
    r = client.post(f"/matriculas/{m}/cancelar")
    assert r.status_code == 200 and r.json()["reprovacao_por_falta"] is True
    hist = client.get(f"/alunos/{aid}/historico").json()
    assert hist[-1]["situacao"] == "reprovado" and hist[-1]["nota"] == 0


def test_regra4_cancelamento_no_prazo_sem_reprovacao(client, api):
    aid = api.aluno("especial")
    m = api.matricular(aid, api.turma(api.disciplina()))
    clock.avancar(timedelta(days=7) - timedelta(minutes=1))
    r = client.post(f"/matriculas/{m}/cancelar")
    assert r.json()["reprovacao_por_falta"] is False
    assert client.get(f"/alunos/{aid}/historico").json() == []


@pytest.mark.parametrize("categoria,limite", [("graduacao", 2), ("pos", 1), ("especial", 0)])
def test_regra4_limite_trancamentos_por_disciplina(client, api, categoria, limite):
    aid = api.aluno(categoria)
    d = api.disciplina()
    for i in range(limite):
        m = api.matricular(aid, api.turma(d, semestre=f"202{i}.1"))
        r = client.post(f"/matriculas/{m}/trancar")
        assert r.status_code == 200 and r.json()["estado"] == "trancada"
    m = api.matricular(aid, api.turma(d, semestre="2030.1"))
    r = client.post(f"/matriculas/{m}/trancar")
    assert r.status_code == 422 and r.json()["erro"] == "limite_trancamentos_excedido"


# ---------------------------------------------------------------------- Regra 5
def test_regra5_turma_com_menos_de_5_confirmadas(client, api):
    d = api.disciplina()
    t4, t5 = api.turma(d), api.turma(d, dia="TER")
    m4 = [api.matricular(api.aluno(), t4) for _ in range(4)]
    pend = api.solicitar(api.aluno(), t4).json()["id"]
    for _ in range(5):
        api.matricular(api.aluno(), t5)
    r = client.post("/semestres/2026.2/encerrar-periodo-matricula")
    assert r.status_code == 200
    assert r.json()["turmas_canceladas"] == [t4] and r.json()["turmas_mantidas"] == [t5]
    assert client.get(f"/turmas/{t4}").json()["estado"] == "cancelada"
    for mid in m4 + [pend]:
        assert client.get(f"/matriculas/{mid}").json()["estado"] == "cancelada"
    assert client.get(f"/turmas/{t5}").json()["estado"] == "aberta"
    assert api.solicitar(api.aluno(), t4).status_code == 409


# ---------------------------------------------------------------------- Regra 6
def test_regra6_conflito_horario(client, api):
    aid = api.aluno()
    t1 = api.turma(api.disciplina(), dia="SEG", inicio="08:00", fim="10:00")
    t2 = api.turma(api.disciplina(), dia="SEG", inicio="09:00", fim="11:00")
    t3 = api.turma(api.disciplina(), dia="SEG", inicio="10:00", fim="12:00")
    api.matricular(aid, t1)
    r = api.solicitar(aid, t2)
    assert r.status_code == 409 and r.json()["erro"] == "conflito_horario"
    assert api.solicitar(aid, t3).status_code == 201  # horarios adjacentes nao conflitam


# ---------------------------------------------------------------------- Regra 7
def test_regra7_tres_trancamentos_no_semestre(client, api):
    aid = api.aluno()
    turmas = _turmas(api, 4)
    ms = [api.matricular(aid, t) for t in turmas]
    for m in ms[:2]:
        assert client.post(f"/matriculas/{m}/trancar").status_code == 200
    assert client.get(f"/alunos/{aid}").json()["situacao"] == "ativo"
    assert client.post(f"/matriculas/{ms[2]}/trancar").status_code == 200
    assert client.get(f"/alunos/{aid}").json()["situacao"] == "trancado"
    assert client.get(f"/matriculas/{ms[3]}").json()["estado"] == "cancelada"
    assert api.solicitar(aid, api.turma(api.disciplina(), dia="SAB")).status_code == 403


# -------------------------------------------------------------------- Relatorios
def test_relatorios(client, api):
    d1 = api.disciplina(departamento="DCC")
    d2 = api.disciplina(departamento="MAT")
    t1, t2 = api.turma(d1, vagas=2), api.turma(d2, vagas=10, dia="TER")
    for _ in range(3):
        api.solicitar(api.aluno(), t1)
    api.matricular(api.aluno(), t2)

    r = client.get("/relatorios/disciplinas-mais-procuradas", params={"semestre": "2026.2"}).json()
    assert [x["disciplina_id"] for x in r["disciplinas"]] == [d1, d2]
    assert r["disciplinas"][0]["solicitacoes"] == 3 and r["disciplinas"][0]["lista_espera"] == 1

    a = api.aluno()
    api.historico(a, d1, "reprovado", 2)
    api.historico(a, d1, "aprovado", 8)
    api.historico(a, d2, "aprovado", 9)
    r = client.get("/relatorios/taxa-reprovacao").json()["disciplinas"]
    assert r[0]["disciplina_id"] == d1 and r[0]["taxa_reprovacao"] == 0.5
    assert r[1]["taxa_reprovacao"] == 0.0

    r = client.get("/relatorios/ocupacao-turmas", params={"semestre": "2026.2"}).json()["departamentos"]
    por = {d["departamento"]: d for d in r}
    assert por["DCC"]["taxa_ocupacao"] == 1.0 and por["MAT"]["taxa_ocupacao"] == 0.1
    assert client.get("/relatorios/disciplinas-mais-procuradas").status_code == 422
