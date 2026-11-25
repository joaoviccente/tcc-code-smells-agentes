def test_crud_aluno(client, api):
    a = api.aluno()
    assert a["situacao"] == "ativo"
    assert client.get(f"/alunos/{a['id']}").status_code == 200
    # duplicidade
    r = client.post("/alunos", json={"nome": "X", "matricula": a["matricula"], "email": "z@uni.br",
                                     "categoria": "pos"})
    assert r.status_code == 409
    # validacao
    r = client.post("/alunos", json={"nome": "X", "matricula": "B1234", "email": "invalido",
                                     "categoria": "doutorado"})
    assert r.status_code == 422
    r = client.patch(f"/alunos/{a['id']}", json={"situacao": "jubilado"})
    assert r.status_code == 200 and r.json()["situacao"] == "jubilado"
    assert client.delete(f"/alunos/{a['id']}").status_code == 204
    assert client.get(f"/alunos/{a['id']}").status_code == 404


def test_crud_disciplina_e_prerequisito(client, api):
    d1, d2 = api.disciplina(), api.disciplina()
    r = client.post("/disciplinas", json={**{k: d1[k] for k in ("codigo", "nome", "creditos", "carga_horaria",
                                                               "departamento")}})
    assert r.status_code == 409
    assert client.post("/disciplinas", json={"codigo": "X1", "nome": "", "creditos": 0, "carga_horaria": -1,
                                             "departamento": "D"}).status_code == 422
    assert client.post(f"/disciplinas/{d2['id']}/pre-requisitos", json={"requisito_id": d1["id"]}).status_code == 201
    assert client.post(f"/disciplinas/{d2['id']}/pre-requisitos", json={"requisito_id": d1["id"]}).status_code == 409
    # ciclo
    assert client.post(f"/disciplinas/{d1['id']}/pre-requisitos", json={"requisito_id": d2["id"]}).status_code == 422
    assert client.delete(f"/disciplinas/{d1['id']}").status_code == 409
    assert client.delete(f"/disciplinas/{d2['id']}/pre-requisitos/{d1['id']}").status_code == 204
    assert client.patch(f"/disciplinas/{d1['id']}", json={"creditos": 6}).json()["creditos"] == 6


def test_crud_turma(client, api):
    t = api.turma(vagas=10)
    assert t["estado"] == "aberta" and t["vagas_disponiveis"] == 10
    # horario invalido / semestre invalido
    r = client.post("/turmas", json={"disciplina_id": t["disciplina_id"], "semestre": "2026.3", "professor": "P",
                                     "vagas": 10, "horario": [{"dia": "dom", "inicio": "10:00", "fim": "09:00"}]})
    assert r.status_code == 422
    assert client.post("/turmas", json={"disciplina_id": 999, "semestre": "2026.1", "professor": "P", "vagas": 1,
                                        "horario": [{"dia": "seg", "inicio": "08:00", "fim": "10:00"}]}
                       ).status_code == 404
    assert client.patch(f"/turmas/{t['id']}", json={"estado": "lotada"}).status_code == 422
    assert client.patch(f"/turmas/{t['id']}", json={"vagas": 20}).json()["vagas"] == 20
    assert client.delete(f"/turmas/{t['id']}").status_code == 204
