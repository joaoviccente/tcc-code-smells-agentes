import pytest

PARAMS = {  # categoria: (limite, prazo, renovacoes)
    "aluno": (3, 7, 2),
    "professor": (8, 30, 4),
    "visitante": (1, 3, 0),
}


@pytest.mark.parametrize("categoria", PARAMS)
def test_prazo_e_limite_por_categoria(api, categoria):
    limite, prazo, _ = PARAMS[categoria]
    u = api.usuario(categoria)
    livro = api.livro()
    exemplares = [api.exemplar(livro["id"]) for _ in range(limite + 1)]
    for ex in exemplares[:limite]:
        emp = api.emprestar(u["id"], ex["id"])
        assert emp["data_retirada"] == "2026-03-02"
        assert emp["estado"] == "ativo" and emp["renovacoes"] == 0
    assert emp["data_prevista"] == {7: "2026-03-09", 30: "2026-04-01", 3: "2026-03-05"}[prazo]
    r = api.c.post("/emprestimos", json={"usuario_id": u["id"], "exemplar_id": exemplares[-1]["id"]})
    assert r.status_code == 409 and "Limite" in r.json()["detail"]
    assert len(api.get(f"/usuarios/{u['id']}/emprestimos")) == limite


@pytest.mark.parametrize("categoria", PARAMS)
def test_limite_de_renovacoes(api, tempo, categoria):
    _, prazo, renovacoes = PARAMS[categoria]
    u = api.usuario(categoria)
    emp = api.emprestar(u["id"], api.exemplar(api.livro()["id"])["id"])
    for i in range(renovacoes):
        tempo.avancar(dias=1)
        r = api.c.post(f"/emprestimos/{emp['id']}/renovacao")
        assert r.status_code == 200, r.text
        assert r.json()["renovacoes"] == i + 1
    r = api.c.post(f"/emprestimos/{emp['id']}/renovacao")
    assert r.status_code == 409 and "renovac" in r.json()["detail"]


def test_renovacao_define_novo_prazo(api, tempo):
    u = api.usuario("aluno")
    emp = api.emprestar(u["id"], api.exemplar(api.livro()["id"])["id"])
    tempo.avancar(dias=5)
    r = api.c.post(f"/emprestimos/{emp['id']}/renovacao")
    assert r.json()["data_prevista"] == "2026-03-14"  # 07/03 + 7 dias


def test_renovacao_negada_com_atraso(api, tempo):
    u = api.usuario("aluno")
    emp = api.emprestar(u["id"], api.exemplar(api.livro()["id"])["id"])
    tempo.avancar(dias=8)
    assert api.get(f"/emprestimos/{emp['id']}")["estado"] == "atrasado"
    r = api.c.post(f"/emprestimos/{emp['id']}/renovacao")
    assert r.status_code == 409 and "atrasado" in r.json()["detail"]


def test_renovacao_negada_com_fila_de_reserva(api):
    livro = api.livro()
    a, b = api.usuario(), api.usuario()
    emp = api.emprestar(a["id"], api.exemplar(livro["id"])["id"])
    api.reservar(b["id"], livro["id"])
    r = api.c.post(f"/emprestimos/{emp['id']}/renovacao")
    assert r.status_code == 409 and "fila" in r.json()["detail"]


def test_emprestimo_negado_a_suspenso(api):
    u = api.usuario(situacao="suspenso")
    ex = api.exemplar(api.livro()["id"])
    r = api.c.post("/emprestimos", json={"usuario_id": u["id"], "exemplar_id": ex["id"]})
    assert r.status_code == 409 and "suspenso" in r.json()["detail"]


def test_emprestimo_exemplar_inexistente_ou_indisponivel(api):
    u1, u2 = api.usuario(), api.usuario()
    livro = api.livro()
    ex = api.exemplar(livro["id"])
    api.emprestar(u1["id"], 999, esperado=404)
    api.emprestar(999, ex["id"], esperado=404)
    api.emprestar(u1["id"], ex["id"])
    api.emprestar(u2["id"], ex["id"], esperado=409)
    reparo = api.exemplar(livro["id"], estado="em_reparo")
    api.emprestar(u2["id"], reparo["id"], esperado=409)
    assert api.c.post("/emprestimos", json={"usuario_id": "x", "exemplar_id": 1}).status_code == 422


def test_devolucao_no_prazo(api, tempo):
    u = api.usuario()
    ex = api.exemplar(api.livro()["id"])
    emp = api.emprestar(u["id"], ex["id"])
    tempo.avancar(dias=7)  # ultimo dia do prazo: sem atraso
    d = api.devolver(emp["id"])
    assert d["estado"] == "devolvido" and d["data_devolucao"] == "2026-03-09"
    assert api.get(f"/usuarios/{u['id']}/multas") == []
    assert api.get(f"/exemplares/{ex['id']}")["estado"] == "disponivel"
    api.devolver(emp["id"], esperado=409)
    assert api.c.post(f"/emprestimos/{emp['id']}/renovacao").status_code == 409
