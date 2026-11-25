def test_livros_mais_emprestados(api, tempo):
    l1, l2 = api.livro(), api.livro()
    e1, e2 = api.exemplar(l1["id"]), api.exemplar(l2["id"])
    u = api.usuario("professor")
    for _ in range(3):
        api.devolver(api.emprestar(u["id"], e1["id"])["id"])
    api.devolver(api.emprestar(u["id"], e2["id"])["id"])
    tempo.avancar(dias=40)
    api.devolver(api.emprestar(u["id"], e2["id"])["id"])

    r = api.get("/relatorios/livros-mais-emprestados?inicio=2026-03-01&fim=2026-03-31")
    assert [(x["livro_id"], x["total_emprestimos"]) for x in r] == [(l1["id"], 3), (l2["id"], 1)]
    r = api.get("/relatorios/livros-mais-emprestados?inicio=2026-04-01&fim=2026-04-30")
    assert [(x["livro_id"], x["total_emprestimos"]) for x in r] == [(l2["id"], 1)]
    assert api.c.get("/relatorios/livros-mais-emprestados?inicio=2026-05-01&fim=2026-04-01").status_code == 422
    assert api.c.get("/relatorios/livros-mais-emprestados").status_code == 422


def test_usuarios_com_mais_atrasos(api, tempo):
    livro = api.livro()
    a, b, c = api.usuario("professor"), api.usuario("professor"), api.usuario("professor")
    ea1 = api.emprestar(a["id"], api.exemplar(livro["id"])["id"])
    ea2 = api.emprestar(a["id"], api.exemplar(livro["id"])["id"])
    eb = api.emprestar(b["id"], api.exemplar(livro["id"])["id"])
    ec = api.emprestar(c["id"], api.exemplar(livro["id"])["id"])
    api.devolver(ec["id"])  # sem atraso
    tempo.avancar(dias=32)
    api.devolver(ea1["id"])  # 2 dias de atraso
    tempo.avancar(dias=3)    # ea2 segue em atraso (5 dias), eb tambem (5 dias)
    r = api.get("/relatorios/usuarios-com-mais-atrasos")
    assert [(x["usuario_id"], x["emprestimos_atrasados"], x["total_dias_atraso"]) for x in r] == [
        (a["id"], 2, 7), (b["id"], 1, 5)]
    assert ea2 and eb


def test_ocupacao_por_area(api):
    comp, mat = api.livro("Computacao"), api.livro("Matematica")
    c1, c2, c3 = (api.exemplar(comp["id"]) for _ in range(3))
    api.exemplar(comp["id"], estado="em_reparo")
    m1 = api.exemplar(mat["id"])
    u = api.usuario("professor")
    api.emprestar(u["id"], c1["id"])
    api.emprestar(u["id"], c2["id"])
    api.c.patch(f"/exemplares/{m1['id']}", json={"estado": "baixado"})
    r = {x["area"]: x for x in api.get("/relatorios/ocupacao-por-area")}
    assert r["Computacao"] == {"area": "Computacao", "total_exemplares": 4, "disponiveis": 1, "emprestados": 2,
                               "reservados": 0, "em_reparo": 1, "taxa_ocupacao": 50.0}
    assert r["Matematica"]["total_exemplares"] == 0 and r["Matematica"]["taxa_ocupacao"] == 0.0
    assert c3
