def test_crud_aluno(client, f):
    a = f.aluno()
    assert a["situacao"] == "ativo"
    assert client.get(f"/alunos/{a['id']}").status_code == 200
    r = client.patch(f"/alunos/{a['id']}", json={"nome": "Novo Nome"})
    assert r.status_code == 200 and r.json()["nome"] == "Novo Nome"
    assert client.delete(f"/alunos/{a['id']}").status_code == 204
    assert client.get(f"/alunos/{a['id']}").status_code == 404
    r = client.get("/matriculas/999")
    assert r.status_code == 404 and r.json()["erro"]["codigo"] == "MATRICULA_NAO_ENCONTRADO"


def test_validacao_aluno(client, f):
    base = {"nome": "Fulano", "matricula": "2026001", "email": "x@uni.br", "categoria": "graduacao"}
    assert client.post("/alunos", json={**base, "categoria": "mestrado"}).status_code == 422
    assert client.post("/alunos", json={**base, "email": "invalido"}).status_code == 422
    assert client.post("/alunos", json={**base, "campo_extra": 1}).status_code == 422
    assert client.post("/alunos", json=base).status_code == 201
    r = client.post("/alunos", json={**base, "email": "y@uni.br"})
    assert r.status_code == 409 and r.json()["erro"]["codigo"] == "ALUNO_DUPLICADO"
    a = client.get("/alunos").json()[0]
    assert client.patch(f"/alunos/{a['id']}", json={"nome": None}).status_code == 422
    assert client.patch(f"/alunos/{a['id']}", json={}).status_code == 422


def test_crud_disciplina_e_pre_requisitos(client, f):
    d1, d2 = f.disciplina(), f.disciplina()
    r = client.post(f"/disciplinas/{d2['id']}/pre-requisitos", json={"requisito_id": d1["id"]})
    assert r.status_code == 201
    assert [p["id"] for p in r.json()["pre_requisitos"]] == [d1["id"]]
    # ciclo
    r = client.post(f"/disciplinas/{d1['id']}/pre-requisitos", json={"requisito_id": d2["id"]})
    assert r.status_code == 422 and r.json()["erro"]["codigo"] == "PRE_REQUISITO_CICLICO"
    # d1 é pré-requisito: não pode ser removida
    assert client.delete(f"/disciplinas/{d1['id']}").status_code == 409
    assert client.post("/disciplinas", json={"codigo": "X", "nome": "Ab", "creditos": 0,
                                             "carga_horaria": 10, "departamento": "DX"}).status_code == 422
    r = client.post("/disciplinas", json={**{k: d1[k] for k in ("nome", "creditos", "carga_horaria", "departamento")},
                                           "codigo": d1["codigo"].lower()})
    assert r.status_code == 409


def test_crud_turma(client, f):
    t = f.turma(vagas=10)
    assert t["estado"] == "aberta" and t["vagas_disponiveis"] == 10
    r = client.patch(f"/turmas/{t['id']}", json={"vagas": 20, "professor": "Prof Y"})
    assert r.status_code == 200 and r.json()["vagas"] == 20
    ruim = {"disciplina_id": t["disciplina"]["id"], "semestre": "2026.3", "professor": "P",
            "vagas": 10, "horarios": [{"dia": "SEG", "inicio": "10:00", "fim": "08:00"}]}
    assert client.post("/turmas", json=ruim).status_code == 422
    sobreposto = {**ruim, "semestre": "2026.1", "professor": "Prof",
                  "horarios": [{"dia": "SEG", "inicio": "08:00", "fim": "10:00"},
                               {"dia": "SEG", "inicio": "09:00", "fim": "11:00"}]}
    assert client.post("/turmas", json=sobreposto).status_code == 422
    assert client.post("/turmas", json={**sobreposto, "disciplina_id": 999,
                                        "horarios": sobreposto["horarios"][:1]}).status_code == 404
    assert client.delete(f"/turmas/{t['id']}").status_code == 204
