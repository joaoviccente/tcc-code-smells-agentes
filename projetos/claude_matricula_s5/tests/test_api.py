from datetime import timedelta

import pytest

from app import clock


# ------------------------------------------------------------------ CRUD e validacao
def test_crud_aluno(client, fab):
    a = fab.aluno()
    assert a["situacao"] == "ativo"
    assert client.get(f"/alunos/{a['id']}").status_code == 200
    r = client.patch(f"/alunos/{a['id']}", json={"nome": "Novo Nome"})
    assert r.status_code == 200 and r.json()["nome"] == "Novo Nome"
    assert client.delete(f"/alunos/{a['id']}").status_code == 204
    assert client.get(f"/alunos/{a['id']}").status_code == 404


def test_validacoes_de_entrada(client, fab):
    base = {"nome": "X Y", "matricula": "ABC123", "email": "x@uni.br", "categoria": "graduacao"}
    assert client.post("/alunos", json={**base, "email": "invalido"}).status_code == 422
    assert client.post("/alunos", json={**base, "categoria": "mestrado"}).status_code == 422
    assert client.post("/alunos", json={**base, "extra": 1}).status_code == 422
    assert client.post("/alunos", json=base).status_code == 201
    r = client.post("/alunos", json={**base, "email": "outro@uni.br"})
    assert r.status_code == 409 and r.json()["erro"] == "MATRICULA_DUPLICADO"
    assert client.patch("/alunos/1", json={"nome": None}).status_code == 422
    d = fab.disciplina()
    assert client.post("/turmas", json={
        "disciplina_id": d["id"], "semestre": "2026.3", "professor": "P", "vagas": 10,
        "horario": [{"dia": "SEG", "inicio": "08:00", "fim": "10:00"}],
    }).status_code == 422
    assert client.post("/turmas", json={
        "disciplina_id": d["id"], "semestre": "2026.1", "professor": "Prof", "vagas": 0,
        "horario": [{"dia": "SEG", "inicio": "08:00", "fim": "10:00"}],
    }).status_code == 422
    assert client.post("/turmas", json={
        "disciplina_id": d["id"], "semestre": "2026.1", "professor": "Prof", "vagas": 5,
        "horario": [{"dia": "SEG", "inicio": "10:00", "fim": "08:00"}],
    }).status_code == 422
    assert client.post("/turmas", json={
        "disciplina_id": 999, "semestre": "2026.1", "professor": "Prof", "vagas": 5,
        "horario": [{"dia": "SEG", "inicio": "08:00", "fim": "10:00"}],
    }).status_code == 404


def test_crud_disciplina_e_pre_requisitos(client, fab):
    a, b = fab.disciplina(), fab.disciplina()
    r = client.post(f"/disciplinas/{b['id']}/pre-requisitos", json={"requisito_id": a["id"]})
    assert r.status_code == 201 and r.json()[0]["id"] == a["id"]
    assert client.post(f"/disciplinas/{b['id']}/pre-requisitos", json={"requisito_id": a["id"]}).status_code == 409
    r = client.post(f"/disciplinas/{a['id']}/pre-requisitos", json={"requisito_id": b["id"]})
    assert r.status_code == 422 and r.json()["erro"] == "PRE_REQUISITO_CICLICO"
    assert client.delete(f"/disciplinas/{a['id']}").status_code == 409
    assert client.delete(f"/disciplinas/{b['id']}/pre-requisitos/{a['id']}").status_code == 204
    assert client.delete(f"/disciplinas/{a['id']}").status_code == 204


def test_crud_turma(client, fab):
    t = fab.turma(vagas=10)
    assert t["estado"] == "aberta" and t["vagas_ocupadas"] == 0
    r = client.patch(f"/turmas/{t['id']}", json={"vagas": 20, "professor": "Prof. Souza"})
    assert r.status_code == 200 and r.json()["vagas"] == 20
    assert client.delete(f"/turmas/{t['id']}").status_code == 204


# ------------------------------------------------------------------ regra 1
def test_aluno_nao_ativo_nao_matricula(client, fab):
    a = fab.aluno(situacao="jubilado")
    r = client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": fab.turma()["id"]})
    assert r.status_code == 422 and r.json()["erro"] == "ALUNO_NAO_ATIVO"


def test_pre_requisitos(client, fab):
    calc1, calc2 = fab.disciplina(), fab.disciplina()
    client.post(f"/disciplinas/{calc2['id']}/pre-requisitos", json={"requisito_id": calc1["id"]})
    t = fab.turma(calc2)
    a = fab.aluno()
    r = client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": t["id"]})
    assert r.status_code == 422 and r.json()["detalhes"]["pendentes"] == [calc1["codigo"]]
    fab.historico(a, calc1, "reprovado")
    assert client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": t["id"]}).status_code == 422
    fab.historico(a, calc1, "aprovado", semestre="2026.1")
    fab.matricular(a, t)


@pytest.mark.parametrize("categoria,maximo", [("graduacao", 28), ("pos", 16), ("especial", 8)])
def test_limite_creditos_por_categoria(client, fab, categoria, maximo):
    a = fab.aluno(categoria)
    for _ in range(maximo // 4):
        fab.matricular(a, fab.turma(fab.disciplina(creditos=4)))
    r = client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": fab.turma(fab.disciplina(creditos=1))["id"]})
    assert r.status_code == 422 and r.json()["erro"] == "LIMITE_CREDITOS_EXCEDIDO"
    assert r.json()["detalhes"]["maximo"] == maximo
    # outro semestre nao conta
    fab.matricular(a, fab.turma(fab.disciplina(creditos=4), semestre="2026.2"))


# ------------------------------------------------------------------ regra 2
def test_lista_de_espera_prioridade_e_prazo_48h(client, fab):
    t = fab.turma(vagas=1)
    ocupante = fab.aluno()
    m0 = fab.matricular(ocupante, t)
    assert client.get(f"/turmas/{t['id']}").json()["estado"] == "lotada"

    esp = fab.aluno("especial")
    grad = fab.aluno("graduacao")
    clock.avancar(timedelta(minutes=1))
    pos = fab.aluno("pos")
    m_esp = fab.matricular(esp, t)
    m_grad = fab.matricular(grad, t)
    clock.avancar(timedelta(minutes=1))
    m_pos = fab.matricular(pos, t)
    assert m_esp["estado"] == "lista_de_espera"
    assert m_pos["posicao_fila"] == 1

    fila = client.get(f"/turmas/{t['id']}/lista-espera").json()["fila"]
    assert [i["matricula_id"] for i in fila] == [m_pos["id"], m_grad["id"], m_esp["id"]]
    assert [i["prioridade"] for i in fila] == ["alta", "media", "baixa"]

    # vaga liberada -> primeiro da fila tem 48h
    r = client.post(f"/matriculas/{m0['id']}/cancelar")
    assert r.status_code == 200
    m = client.get(f"/matriculas/{m_pos['id']}").json()
    assert m["estado"] == "solicitada" and m["prazo_confirmacao"] is not None

    # prazo esgotado -> cancelada, vez passa ao proximo
    clock.avancar(timedelta(hours=48, seconds=1))
    assert client.get(f"/matriculas/{m_pos['id']}").json()["estado"] == "cancelada"
    r = client.post(f"/matriculas/{m_pos['id']}/confirmar")
    assert r.status_code == 409 and r.json()["erro"] == "PRAZO_CONFIRMACAO_EXPIRADO"
    assert client.get(f"/matriculas/{m_grad['id']}").json()["estado"] == "solicitada"

    # proximo confirma dentro do prazo
    clock.avancar(timedelta(hours=47))
    r = client.post(f"/matriculas/{m_grad['id']}/confirmar")
    assert r.status_code == 200 and r.json()["estado"] == "confirmada"
    assert client.get(f"/turmas/{t['id']}/lista-espera").json()["fila"][0]["matricula_id"] == m_esp["id"]


def test_expiracoes_em_cascata(client, fab):
    t = fab.turma(vagas=1)
    m0 = fab.matricular(fab.aluno(), t)
    m1 = fab.matricular(fab.aluno(), t)
    m2 = fab.matricular(fab.aluno(), t)
    m3 = fab.matricular(fab.aluno(), t)
    client.post(f"/matriculas/{m0['id']}/cancelar")
    clock.avancar(timedelta(hours=100))  # 2 prazos de 48h esgotados
    estados = [client.get(f"/matriculas/{m['id']}").json()["estado"] for m in (m1, m2, m3)]
    assert estados == ["cancelada", "cancelada", "solicitada"]


# ------------------------------------------------------------------ regra 3
def test_tres_reprovacoes_impedem_matricula(client, fab):
    d = fab.disciplina()
    a = fab.aluno()
    for sem in ("2024.1", "2024.2"):
        fab.historico(a, d, "reprovado", semestre=sem)
    t = fab.turma(d)
    m = fab.matricular(a, t, confirmar=False)
    client.post(f"/matriculas/{m['id']}/cancelar")
    fab.historico(a, d, "reprovado", semestre="2025.1")
    r = client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": t["id"]})
    assert r.status_code == 422 and r.json()["erro"] == "LIMITE_REPROVACOES"


# ------------------------------------------------------------------ regra 4
@pytest.mark.parametrize("categoria,dias", [("graduacao", 15), ("pos", 30)])
def test_trancamento_dentro_e_fora_do_prazo(client, fab, categoria, dias):
    a = fab.aluno(categoria)
    m = fab.matricular(a, fab.turma())
    clock.avancar(timedelta(days=dias, seconds=1))
    r = client.post(f"/matriculas/{m['id']}/trancar")
    assert r.status_code == 422 and r.json()["erro"] == "PRAZO_TRANCAMENTO_EXPIRADO"

    m2 = fab.matricular(a, fab.turma())
    clock.avancar(timedelta(days=dias, minutes=-1))
    r = client.post(f"/matriculas/{m2['id']}/trancar")
    assert r.status_code == 200 and r.json()["matricula"]["estado"] == "trancada"
    hist = client.get(f"/alunos/{a['id']}/historico").json()
    assert hist["resumo"]["trancado"] == 1


def test_especial_nao_pode_trancar(client, fab):
    m = fab.matricular(fab.aluno("especial"), fab.turma())
    r = client.post(f"/matriculas/{m['id']}/trancar")
    assert r.status_code == 422 and r.json()["erro"] == "TRANCAMENTO_NAO_PERMITIDO"


@pytest.mark.parametrize("categoria,limite", [("graduacao", 2), ("pos", 1)])
def test_limite_trancamentos_por_disciplina(client, fab, categoria, limite):
    a = fab.aluno(categoria)
    d = fab.disciplina()
    for i in range(limite):
        m = fab.matricular(a, fab.turma(d, semestre=f"202{i}.1"))
        assert client.post(f"/matriculas/{m['id']}/trancar").status_code == 200
    m = fab.matricular(a, fab.turma(d, semestre="2029.1"))
    r = client.post(f"/matriculas/{m['id']}/trancar")
    assert r.status_code == 422 and r.json()["erro"] == "LIMITE_TRANCAMENTOS_DISCIPLINA"


@pytest.mark.parametrize("categoria,dias", [("graduacao", 15), ("pos", 30), ("especial", 7)])
def test_cancelamento_fora_do_prazo_registra_reprovacao(client, fab, categoria, dias):
    a = fab.aluno(categoria)
    m1 = fab.matricular(a, fab.turma())
    m2 = fab.matricular(a, fab.turma())
    clock.avancar(timedelta(days=dias, minutes=-1))
    r = client.post(f"/matriculas/{m1['id']}/cancelar")
    assert r.status_code == 200 and r.json()["avisos"] == []
    clock.avancar(timedelta(minutes=2))
    r = client.post(f"/matriculas/{m2['id']}/cancelar")
    assert r.status_code == 200 and "reprovacao por falta" in r.json()["avisos"][0]
    hist = client.get(f"/alunos/{a['id']}/historico").json()
    assert hist["resumo"]["reprovado"] == 1
    assert hist["registros"][0]["por_falta"] is True and hist["registros"][0]["nota"] == 0


# ------------------------------------------------------------------ regra 5
def test_encerramento_periodo_cancela_turmas_com_menos_de_5(client, fab):
    t4, t5 = fab.turma(), fab.turma()
    for _ in range(4):
        fab.matricular(fab.aluno(), t4)
    pendente = fab.matricular(fab.aluno(), t4, confirmar=False)
    for _ in range(5):
        fab.matricular(fab.aluno(), t5)
    r = client.post("/periodos/2026.1/encerrar-matriculas")
    assert r.status_code == 200
    assert r.json()["turmas_canceladas"] == [t4["id"]] and r.json()["turmas_mantidas"] == [t5["id"]]
    assert client.get(f"/turmas/{t4['id']}").json()["estado"] == "cancelada"
    estados = {m["estado"] for m in client.get(f"/turmas/{t4['id']}/matriculas").json()}
    assert estados == {"cancelada"}
    assert client.get(f"/matriculas/{pendente['id']}").json()["estado"] == "cancelada"
    assert client.get(f"/turmas/{t5['id']}").json()["estado"] == "aberta"


# ------------------------------------------------------------------ regra 6
def test_conflito_de_horario(client, fab):
    a = fab.aluno()
    t1 = fab.turma(horario=[{"dia": "TER", "inicio": "08:00", "fim": "10:00"}])
    t2 = fab.turma(horario=[{"dia": "TER", "inicio": "09:30", "fim": "11:00"}])
    t3 = fab.turma(horario=[{"dia": "TER", "inicio": "10:00", "fim": "12:00"}])
    fab.matricular(a, t1)
    r = client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": t2["id"]})
    assert r.status_code == 409 and r.json()["erro"] == "CONFLITO_HORARIO"
    fab.matricular(a, t3)  # termina 10:00 / comeca 10:00: sem conflito


# ------------------------------------------------------------------ regra 7
def test_tres_trancamentos_no_semestre_trancam_aluno(client, fab):
    a = fab.aluno()
    ms = [fab.matricular(a, fab.turma()) for _ in range(4)]
    t_espera = fab.turma(vagas=1)
    fab.matricular(fab.aluno(), t_espera)
    na_fila = fab.matricular(a, t_espera)
    assert na_fila["estado"] == "lista_de_espera"
    for m in ms[:2]:
        assert client.post(f"/matriculas/{m['id']}/trancar").status_code == 200
    assert client.get(f"/alunos/{a['id']}").json()["situacao"] == "ativo"
    r = client.post(f"/matriculas/{ms[2]['id']}/trancar")
    assert r.status_code == 200 and r.json()["avisos"]
    assert client.get(f"/alunos/{a['id']}").json()["situacao"] == "trancado"
    assert client.get(f"/matriculas/{ms[3]['id']}").json()["estado"] == "cancelada"
    assert client.get(f"/matriculas/{na_fila['id']}").json()["estado"] == "cancelada"
    r = client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": fab.turma()["id"]})
    assert r.status_code == 422


# ------------------------------------------------------------------ outros
def test_transicoes_invalidas_e_duplicidade(client, fab):
    a, t = fab.aluno(), fab.turma()
    m = fab.matricular(a, t)
    assert client.post("/matriculas", json={"aluno_id": a["id"], "turma_id": t["id"]}).status_code == 409
    assert client.post(f"/matriculas/{m['id']}/confirmar").status_code == 409
    client.post(f"/matriculas/{m['id']}/cancelar")
    assert client.post(f"/matriculas/{m['id']}/cancelar").status_code == 409
    assert client.post("/matriculas/999/confirmar").status_code == 404


def test_listar_matriculas_por_aluno(client, fab):
    a = fab.aluno()
    fab.matricular(a, fab.turma())
    fab.matricular(a, fab.turma(semestre="2026.2"))
    assert len(client.get(f"/alunos/{a['id']}/matriculas").json()) == 2
    assert len(client.get(f"/alunos/{a['id']}/matriculas?semestre=2026.2").json()) == 1


def test_relatorios(client, fab):
    d1 = fab.disciplina(departamento="DCC")
    d2 = fab.disciplina(departamento="MAT")
    t1, t2 = fab.turma(d1, vagas=2), fab.turma(d2, vagas=10)
    for _ in range(3):
        fab.matricular(fab.aluno(), t1)
    fab.matricular(fab.aluno(), t2)

    r = client.get("/relatorios/disciplinas-mais-procuradas?semestre=2026.1").json()
    assert r[0]["codigo"] == d1["codigo"] and r[0]["total_solicitacoes"] == 3 and r[0]["lista_de_espera"] == 1

    a = fab.aluno()
    fab.historico(a, d1, "reprovado", semestre="2024.1")
    fab.historico(a, d1, "aprovado", semestre="2024.2")
    fab.historico(fab.aluno(), d1, "trancado")
    r = client.get("/relatorios/taxa-reprovacao").json()
    assert r[0]["taxa_reprovacao"] == 0.5 and r[0]["trancados"] == 1

    r = client.get("/relatorios/ocupacao-turmas?semestre=2026.1").json()
    por_dep = {d["departamento"]: d for d in r}
    assert por_dep["DCC"]["taxa_ocupacao"] == 1.0
    assert por_dep["MAT"]["taxa_ocupacao"] == 0.1
    assert client.get("/relatorios/ocupacao-turmas").status_code == 422
