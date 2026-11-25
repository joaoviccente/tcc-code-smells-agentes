def test_crud_aluno(client, fab):
    a = fab.aluno()
    assert a["situacao"] == "ativo"
    assert client.get(f"/alunos/{a['id']}").status_code == 200
    r = client.patch(f"/alunos/{a['id']}", json={"nome": "Novo Nome"})
    assert r.status_code == 200 and r.json()["nome"] == "Novo Nome"
    assert client.delete(f"/alunos/{a['id']}").status_code == 204
    assert client.get(f"/alunos/{a['id']}").status_code == 404


def test_aluno_duplicado_e_validacao(client, fab):
    a = fab.aluno()
    r = client.post("/alunos", json={"nome": "X", "matricula": a["matricula"],
                                     "email": "outro@uni.br", "categoria": "pos"})
    assert r.status_code == 409
    r = client.post("/alunos", json={"nome": "X", "matricula": "B123",
                                     "email": "invalido", "categoria": "pos"})
    assert r.status_code == 422
    r = client.post("/alunos", json={"nome": "X", "matricula": "B123",
                                     "email": "x@uni.br", "categoria": "mestrado"})
    assert r.status_code == 422


def test_crud_disciplina_e_prereq(client, fab):
    d1, d2, d3 = fab.disciplina(), fab.disciplina(), fab.disciplina()
    assert client.post("/disciplinas", json={**{k: d1[k] for k in
                       ("codigo", "nome", "creditos", "carga_horaria", "departamento")}}
                       ).status_code == 409
    assert client.post("/disciplinas", json={"codigo": "X1", "nome": "n", "creditos": 0,
                                             "carga_horaria": 10, "departamento": "D"}
                       ).status_code == 422
    assert client.post(f"/disciplinas/{d2['id']}/pre-requisitos",
                       json={"requisito_id": d1["id"]}).status_code == 201
    assert client.post(f"/disciplinas/{d3['id']}/pre-requisitos",
                       json={"requisito_id": d2["id"]}).status_code == 201
    # ciclo d1 -> d3 -> d2 -> d1
    r = client.post(f"/disciplinas/{d1['id']}/pre-requisitos", json={"requisito_id": d3["id"]})
    assert r.status_code == 422 and r.json()["erro"] == "PRE_REQUISITO_CICLICO"
    assert client.delete(f"/disciplinas/{d1['id']}").status_code == 409
    assert [d["id"] for d in client.get(f"/disciplinas/{d2['id']}/pre-requisitos").json()] == [d1["id"]]


def test_crud_turma_validacoes(client, fab):
    d = fab.disciplina()
    base = {"disciplina_id": d["id"], "semestre": "2026.1", "professor": "P", "vagas": 10,
            "horario": [{"dia": "seg", "inicio": "10:00", "fim": "08:00"}]}
    assert client.post("/turmas", json=base).status_code == 422
    assert client.post("/turmas", json={**base, "semestre": "2026.3"}).status_code == 422
    assert client.post("/turmas", json={**base, "disciplina_id": 999,
                       "horario": [{"dia": "seg", "inicio": "08:00", "fim": "10:00"}]}
                       ).status_code == 404
    t = fab.turma(d)
    assert t["estado"] == "aberta"
    r = client.patch(f"/turmas/{t['id']}", json={"vagas": 40})
    assert r.status_code == 200 and r.json()["vagas"] == 40
    assert client.delete(f"/turmas/{t['id']}").status_code == 204
