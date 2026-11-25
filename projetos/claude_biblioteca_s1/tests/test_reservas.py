def _cenario(api, n_reservantes=2):
    livro = api.livro()
    ex = api.exemplar(livro["id"])
    dono = api.usuario()
    emp = api.emprestar(dono["id"], ex["id"])
    reservantes = [api.usuario() for _ in range(n_reservantes)]
    reservas = [api.reservar(u["id"], livro["id"]) for u in reservantes]
    return livro, ex, emp, reservantes, reservas


def test_reserva_negada_com_exemplar_disponivel(api):
    livro = api.livro()
    api.exemplar(livro["id"])
    r = api.c.post("/reservas", json={"usuario_id": api.usuario()["id"], "livro_id": livro["id"]})
    assert r.status_code == 409


def test_reserva_negada_sem_exemplar_reservavel(api):
    livro = api.livro()
    api.exemplar(livro["id"], estado="em_reparo")
    api.reservar(api.usuario()["id"], livro["id"], esperado=409)
    api.reservar(api.usuario()["id"], api.livro()["id"], esperado=409)  # sem exemplares
    api.reservar(api.usuario()["id"], 999, esperado=404)


def test_fila_por_ordem_de_chegada(api, tempo):
    livro, ex, emp, us, rs = _cenario(api, 3)
    assert [r["posicao"] for r in rs] == [1, 2, 3]
    fila = api.get(f"/livros/{livro['id']}/reservas")
    assert [r["usuario_id"] for r in fila] == [u["id"] for u in us]
    api.reservar(us[0]["id"], livro["id"], esperado=409)  # duplicada

    tempo.avancar(dias=2)
    api.devolver(emp["id"])
    fila = api.get(f"/livros/{livro['id']}/reservas")
    assert fila[0]["estado"] == "disponivel" and fila[0]["exemplar_id"] == ex["id"]
    assert fila[0]["expira_em"] == "2026-03-06T10:00:00"  # 48 horas
    assert [r["estado"] for r in fila[1:]] == ["aguardando", "aguardando"]
    assert api.get(f"/exemplares/{ex['id']}")["estado"] == "reservado"

    # somente o primeiro da fila pode retirar
    api.emprestar(us[1]["id"], ex["id"], esperado=409)
    novo = api.emprestar(us[0]["id"], ex["id"])
    assert api.get(f"/reservas/{rs[0]['id']}")["estado"] == "atendida"
    fila = api.get(f"/livros/{livro['id']}/reservas")
    assert [(r["usuario_id"], r["posicao"]) for r in fila] == [(us[1]["id"], 1), (us[2]["id"], 2)]
    assert novo["estado"] == "ativo"


def test_reserva_expira_apos_48h_e_passa_ao_proximo(api, tempo):
    livro, ex, emp, us, rs = _cenario(api, 2)
    api.devolver(emp["id"])
    tempo.avancar(horas=47, )
    assert api.get(f"/reservas/{rs[0]['id']}")["estado"] == "disponivel"
    tempo.avancar(horas=1)
    assert api.get(f"/reservas/{rs[0]['id']}")["estado"] == "expirada"
    seguinte = api.get(f"/reservas/{rs[1]['id']}")
    assert seguinte["estado"] == "disponivel" and seguinte["posicao"] == 1
    api.emprestar(us[0]["id"], ex["id"], esperado=409)

    tempo.avancar(horas=48)
    assert api.get(f"/reservas/{rs[1]['id']}")["estado"] == "expirada"
    assert api.get(f"/exemplares/{ex['id']}")["estado"] == "disponivel"
    assert api.get(f"/livros/{livro['id']}/reservas") == []


def test_cancelamento_de_reserva(api):
    livro, ex, emp, us, rs = _cenario(api, 2)
    api.devolver(emp["id"])
    r = api.c.post(f"/reservas/{rs[0]['id']}/cancelamento")
    assert r.status_code == 200 and r.json()["estado"] == "cancelada"
    assert api.get(f"/reservas/{rs[1]['id']}")["estado"] == "disponivel"
    assert api.c.post(f"/reservas/{rs[0]['id']}/cancelamento").status_code == 409
    api.c.post(f"/reservas/{rs[1]['id']}/cancelamento")
    assert api.get(f"/exemplares/{ex['id']}")["estado"] == "disponivel"
    assert len(api.get(f"/livros/{livro['id']}/reservas?incluir_encerradas=true")) == 2


def test_baixa_do_ultimo_exemplar_cancela_reservas(api):
    livro, ex, emp, us, rs = _cenario(api, 2)
    api.devolver(emp["id"])  # exemplar fica reservado para o 1o da fila
    r = api.c.patch(f"/exemplares/{ex['id']}", json={"estado": "baixado"})
    assert r.status_code == 200
    assert {api.get(f"/reservas/{r['id']}")["estado"] for r in rs} == {"cancelada"}


def test_baixa_com_outro_exemplar_mantem_reservas(api):
    livro = api.livro()
    ex1, ex2 = api.exemplar(livro["id"]), api.exemplar(livro["id"])
    emp1 = api.emprestar(api.usuario()["id"], ex1["id"])
    api.emprestar(api.usuario()["id"], ex2["id"])
    reserva = api.reservar(api.usuario()["id"], livro["id"])
    api.devolver(emp1["id"])
    assert api.get(f"/reservas/{reserva['id']}")["exemplar_id"] == ex1["id"]
    api.c.patch(f"/exemplares/{ex1['id']}", json={"estado": "baixado"})
    # ex2 continua emprestado: a reserva volta a aguardar, mantendo a posicao
    r = api.get(f"/reservas/{reserva['id']}")
    assert (r["estado"], r["posicao"], r["exemplar_id"]) == ("aguardando", 1, None)


def test_devolucao_com_mais_de_60_dias_cancela_reservas(api, tempo):
    livro, ex, emp, us, rs = _cenario(api, 2)
    tempo.avancar(dias=7 + 61)
    api.devolver(emp["id"])
    assert api.get(f"/exemplares/{ex['id']}")["estado"] == "baixado"
    assert {api.get(f"/reservas/{r['id']}")["estado"] for r in rs} == {"cancelada"}


def test_exemplar_retornando_do_reparo_atende_fila(api):
    livro, ex, emp, us, rs = _cenario(api, 1)
    reparo = api.exemplar(livro["id"], estado="em_reparo")
    api.c.patch(f"/exemplares/{reparo['id']}", json={"estado": "disponivel"})
    assert api.get(f"/exemplares/{reparo['id']}")["estado"] == "reservado"
    assert api.get(f"/reservas/{rs[0]['id']}")["exemplar_id"] == reparo["id"]
