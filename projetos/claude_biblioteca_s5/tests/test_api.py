from app import clock


# ------------------------------------------------------------------- CRUD
def test_crud_usuario(client, f):
    u = f.usuario("professor")
    assert u["situacao"] == "ativo"
    assert client.get(f"/usuarios/{u['id']}").status_code == 200
    r = client.patch(f"/usuarios/{u['id']}", json={"nome": "Novo Nome"})
    assert r.status_code == 200 and r.json()["nome"] == "Novo Nome"
    assert client.delete(f"/usuarios/{u['id']}").status_code == 204
    assert client.get(f"/usuarios/{u['id']}").status_code == 404


def test_validacao_usuario(client, f):
    u = f.usuario()
    base = {"nome": "X", "email": "x@universidade.edu.br", "matricula": "X1", "categoria": "aluno"}
    assert client.post("/usuarios", json={**base, "categoria": "reitor"}).status_code == 422
    assert client.post("/usuarios", json={**base, "email": "invalido"}).status_code == 422
    assert client.post("/usuarios", json={**base, "nome": "  "}).status_code == 422
    assert client.post("/usuarios", json={**base, "extra": 1}).status_code == 422
    assert client.post("/usuarios", json={**base, "email": u["email"]}).status_code == 409
    assert client.post("/usuarios", json={**base, "matricula": u["matricula"]}).status_code == 409


def test_crud_livro_e_exemplar(client, f):
    base = {"titulo": "T", "autor": "A", "isbn": "978-85-7522-000-0", "ano": 2020, "area_conhecimento": "X"}
    assert client.post("/livros", json=base).status_code == 422  # digito verificador errado
    r = client.post("/livros", json={**base, "isbn": "0-306-40615-2"})
    assert r.status_code == 201 and r.json()["isbn"] == "0306406152"
    assert client.post("/livros", json={**base, "isbn": "0306406152"}).status_code == 409
    assert client.post("/livros", json={**base, "isbn": "9780306406157", "ano": 3000}).status_code == 422
    livro = r.json()
    ex = f.exemplar(livro["id"])
    assert ex["estado"] == "disponivel"
    assert client.post("/exemplares", json={"livro_id": 999, "codigo_tombo": "Z"}).status_code == 404
    assert client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "Z",
                                            "estado": "emprestado"}).status_code == 422
    assert client.delete(f"/livros/{livro['id']}").status_code == 409
    assert client.delete(f"/exemplares/{ex['id']}").status_code == 204
    assert client.delete(f"/livros/{livro['id']}").status_code == 204


# ------------------------------------------------------ Regras por categoria
def test_prazos_por_categoria(client, f):
    livro = f.livro()
    for cat, prevista in (("aluno", "2026-03-09"), ("professor", "2026-04-01"), ("visitante", "2026-03-05")):
        u = f.usuario(cat)
        emp = f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
        assert emp["data_prevista"] == prevista
        assert emp["estado"] == "ativo"


def test_limite_de_exemplares(client, f):
    livro = f.livro()
    for cat, limite in (("aluno", 3), ("professor", 8), ("visitante", 1)):
        u = f.usuario(cat)
        for _ in range(limite):
            f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
        r = client.post("/emprestimos", json={"usuario_id": u["id"],
                                              "exemplar_id": f.exemplar(livro["id"])["id"]})
        assert r.status_code == 409 and r.json()["codigo"] == "limite_exemplares"


def test_usuario_suspenso_nao_empresta(client, f):
    u = f.usuario(situacao="suspenso")
    ex = f.exemplar(f.livro()["id"])
    r = f.emprestar(u["id"], ex["id"], esperado=409)
    assert r["codigo"] == "usuario_suspenso"


def test_exemplar_indisponivel(client, f):
    livro = f.livro()
    ex = f.exemplar(livro["id"], estado="em_reparo")
    assert f.emprestar(f.usuario()["id"], ex["id"], esperado=409)["codigo"] == "exemplar_indisponivel"
    ex2 = f.exemplar(livro["id"])
    f.emprestar(f.usuario()["id"], ex2["id"])
    assert f.emprestar(f.usuario()["id"], ex2["id"], esperado=409)["codigo"] == "exemplar_indisponivel"


# ------------------------------------------------------------------- Multas
def _emprestar_e_devolver_com_atraso(client, f, categoria, dias):
    u = f.usuario(categoria)
    emp = f.emprestar(u["id"], f.exemplar(f.livro()["id"])["id"])
    prazo = {"aluno": 7, "professor": 30, "visitante": 3}[categoria]
    clock.avancar(days=prazo + dias)
    dev = f.devolver(emp["id"])
    return u, dev


def test_multa_aluno_por_dia(client, f):
    u, dev = _emprestar_e_devolver_com_atraso(client, f, "aluno", 5)
    assert dev["dias_atraso"] == 5
    assert dev["multa"]["valor"] == 5.0 and dev["multa"]["estado"] == "aberta"


def test_multa_teto_aluno(client, f):
    _, dev = _emprestar_e_devolver_com_atraso(client, f, "aluno", 40)
    assert dev["multa"]["valor"] == 30.0


def test_multa_visitante(client, f):
    _, dev = _emprestar_e_devolver_com_atraso(client, f, "visitante", 3)
    assert dev["multa"]["valor"] == 6.0
    _, dev = _emprestar_e_devolver_com_atraso(client, f, "visitante", 12)
    assert dev["multa"]["valor"] == 20.0


def test_multa_professor_perdoada_ate_2_dias(client, f):
    _, dev = _emprestar_e_devolver_com_atraso(client, f, "professor", 2)
    assert dev["multa"]["valor"] == 1.0 and dev["multa"]["estado"] == "perdoada"
    _, dev = _emprestar_e_devolver_com_atraso(client, f, "professor", 3)
    assert dev["multa"]["valor"] == 1.5 and dev["multa"]["estado"] == "aberta"
    _, dev = _emprestar_e_devolver_com_atraso(client, f, "professor", 15)
    assert dev["multa"]["valor"] == 7.5


def test_sem_atraso_sem_multa(client, f):
    u = f.usuario()
    emp = f.emprestar(u["id"], f.exemplar(f.livro()["id"])["id"])
    clock.avancar(days=7)
    assert f.devolver(emp["id"])["multa"] is None


def test_multa_aberta_bloqueia_e_pagamento_libera(client, f):
    u, dev = _emprestar_e_devolver_com_atraso(client, f, "aluno", 2)
    ex = f.exemplar(f.livro()["id"])
    assert f.emprestar(u["id"], ex["id"], esperado=409)["codigo"] == "multa_aberta"
    multas = client.get(f"/usuarios/{u['id']}/multas").json()
    assert len(multas) == 1
    r = client.post(f"/multas/{multas[0]['id']}/pagamento")
    assert r.status_code == 200 and r.json()["estado"] == "paga"
    assert client.post(f"/multas/{multas[0]['id']}/pagamento").status_code == 409
    f.emprestar(u["id"], ex["id"])


# ----------------------------------------------------------------- Suspensao
def test_suspensao_por_atraso_superior_a_15_dias(client, f):
    u = f.usuario("aluno")
    emp = f.emprestar(u["id"], f.exemplar(f.livro()["id"])["id"])
    clock.avancar(days=7 + 15)
    assert client.get(f"/usuarios/{u['id']}").json()["situacao"] == "ativo"  # 15 dias: nao suspende
    clock.avancar(days=1)
    assert client.get(f"/usuarios/{u['id']}").json()["situacao"] == "suspenso"  # 16 dias
    f.devolver(emp["id"])
    usuario = client.get(f"/usuarios/{u['id']}").json()
    assert usuario["suspenso_ate"] == "2026-04-26T10:00:00"  # devolucao (25/03) + 2 x 16 dias
    clock.avancar(days=31)
    assert client.get(f"/usuarios/{u['id']}").json()["situacao"] == "suspenso"
    clock.avancar(days=1)
    usuario = client.get(f"/usuarios/{u['id']}").json()
    assert usuario["situacao"] == "ativo" and usuario["suspenso_ate"] is None


def test_atraso_de_15_dias_nao_suspende(client, f):
    u, dev = _emprestar_e_devolver_com_atraso(client, f, "aluno", 15)
    assert client.get(f"/usuarios/{u['id']}").json()["situacao"] == "ativo"


# ----------------------------------------------------------------- Renovacao
def test_renovacoes_por_categoria(client, f):
    livro = f.livro()
    for cat, maximo in (("aluno", 2), ("professor", 4), ("visitante", 0)):
        u = f.usuario(cat)
        emp = f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
        for i in range(maximo):
            r = client.post(f"/emprestimos/{emp['id']}/renovacao")
            assert r.status_code == 200 and r.json()["numero_renovacoes"] == i + 1
        r = client.post(f"/emprestimos/{emp['id']}/renovacao")
        assert r.status_code == 409 and r.json()["codigo"] == "limite_renovacoes"


def test_renovacao_estende_prazo(client, f):
    u = f.usuario("aluno")
    emp = f.emprestar(u["id"], f.exemplar(f.livro()["id"])["id"])
    clock.avancar(days=5)
    r = client.post(f"/emprestimos/{emp['id']}/renovacao").json()
    assert r["data_prevista"] == "2026-03-14"


def test_renovacao_negada_se_atrasado(client, f):
    u = f.usuario("aluno")
    emp = f.emprestar(u["id"], f.exemplar(f.livro()["id"])["id"])
    clock.avancar(days=8)
    r = client.post(f"/emprestimos/{emp['id']}/renovacao")
    assert r.status_code == 409 and r.json()["codigo"] == "emprestimo_atrasado"
    assert client.get(f"/emprestimos/{emp['id']}").json()["estado"] == "atrasado"


def test_renovacao_negada_com_fila(client, f):
    livro = f.livro()
    u = f.usuario("professor")
    emp = f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
    f.reservar(f.usuario()["id"], livro["id"])
    r = client.post(f"/emprestimos/{emp['id']}/renovacao")
    assert r.status_code == 409 and r.json()["codigo"] == "fila_reserva"


# ------------------------------------------------------------------ Reservas
def test_fila_de_reserva_e_expiracao(client, f):
    livro = f.livro()
    ex = f.exemplar(livro["id"])
    dono, a, b = f.usuario(), f.usuario(), f.usuario()
    emp = f.emprestar(dono["id"], ex["id"])
    ra = f.reservar(a["id"], livro["id"])
    clock.avancar(minutes=1)
    rb = f.reservar(b["id"], livro["id"])
    assert (ra["posicao_fila"], rb["posicao_fila"]) == (1, 2)
    f.reservar(a["id"], livro["id"], esperado=409)  # duplicada

    clock.avancar(days=1)
    f.devolver(emp["id"])
    fila = client.get(f"/livros/{livro['id']}/reservas").json()
    assert fila[0]["estado"] == "disponivel" and fila[0]["usuario_id"] == a["id"]
    assert fila[0]["expira_em"] == "2026-03-05T10:01:00"  # devolucao + 48h
    assert client.get(f"/exemplares/{ex['id']}").json()["estado"] == "reservado"
    # Outro usuario nao pode levar o exemplar reservado
    assert f.emprestar(b["id"], ex["id"], esperado=409)["codigo"] == "exemplar_reservado"

    clock.avancar(hours=48)  # prazo esgotado: expira e passa para B
    fila = client.get(f"/livros/{livro['id']}/reservas?incluir_encerradas=true").json()
    estados = {r["usuario_id"]: r["estado"] for r in fila}
    assert estados == {a["id"]: "expirada", b["id"]: "disponivel"}
    assert f.emprestar(a["id"], ex["id"], esperado=409)["codigo"] == "exemplar_reservado"
    f.emprestar(b["id"], ex["id"])
    assert client.get(f"/reservas/{rb['id']}").json()["estado"] == "atendida"
    assert client.get(f"/livros/{livro['id']}/reservas").json() == []


def test_reserva_disponivel_dentro_de_48h(client, f):
    livro = f.livro()
    ex = f.exemplar(livro["id"])
    emp = f.emprestar(f.usuario()["id"], ex["id"])
    a = f.usuario()
    r = f.reservar(a["id"], livro["id"])
    f.devolver(emp["id"])
    r = client.get(f"/reservas/{r['id']}").json()
    assert r["expira_em"] == "2026-03-04T10:00:00"
    clock.avancar(hours=47, minutes=59)
    f.emprestar(a["id"], ex["id"])


def test_cancelamento_passa_vez(client, f):
    livro = f.livro()
    ex = f.exemplar(livro["id"])
    emp = f.emprestar(f.usuario()["id"], ex["id"])
    a, b = f.usuario(), f.usuario()
    ra = f.reservar(a["id"], livro["id"])
    rb = f.reservar(b["id"], livro["id"])
    f.devolver(emp["id"])
    r = client.post(f"/reservas/{ra['id']}/cancelamento")
    assert r.status_code == 200 and r.json()["estado"] == "cancelada"
    rb = client.get(f"/reservas/{rb['id']}").json()
    assert rb["estado"] == "disponivel" and rb["posicao_fila"] == 1
    assert client.post(f"/reservas/{ra['id']}/cancelamento").status_code == 409


def test_reserva_negada_com_exemplar_disponivel_ou_em_reparo(client, f):
    livro = f.livro()
    ex = f.exemplar(livro["id"])
    assert f.reservar(f.usuario()["id"], livro["id"], esperado=409)["codigo"] == "exemplar_disponivel"
    client.patch(f"/exemplares/{ex['id']}", json={"estado": "em_reparo"})
    assert f.reservar(f.usuario()["id"], livro["id"], esperado=409)["codigo"] == "sem_exemplar_reservavel"


def test_baixa_do_ultimo_exemplar_cancela_reservas(client, f):
    livro = f.livro()
    ex1, ex2 = f.exemplar(livro["id"]), f.exemplar(livro["id"])
    e1 = f.emprestar(f.usuario()["id"], ex1["id"])
    f.emprestar(f.usuario()["id"], ex2["id"])
    r = f.reservar(f.usuario()["id"], livro["id"])
    f.devolver(e1["id"])  # ex1 fica reservado para r
    assert client.patch(f"/exemplares/{ex1['id']}", json={"estado": "baixado"}).status_code == 200
    # ainda ha ex2 (emprestado): reserva volta a aguardar
    assert client.get(f"/reservas/{r['id']}").json()["estado"] == "aguardando"
    # ex2 nao pode ser baixado enquanto emprestado
    assert client.patch(f"/exemplares/{ex2['id']}", json={"estado": "baixado"}).status_code == 409


def test_baixa_cancela_reservas_quando_nao_resta_exemplar(client, f):
    livro = f.livro()
    ex = f.exemplar(livro["id"])
    emp = f.emprestar(f.usuario()["id"], ex["id"])
    r = f.reservar(f.usuario()["id"], livro["id"])
    f.devolver(emp["id"])
    client.patch(f"/exemplares/{ex['id']}", json={"estado": "baixado"})
    assert client.get(f"/reservas/{r['id']}").json()["estado"] == "cancelada"
    assert client.patch(f"/exemplares/{ex['id']}", json={"estado": "disponivel"}).status_code == 409


def test_exemplar_novo_atende_fila(client, f):
    livro = f.livro()
    f.emprestar(f.usuario()["id"], f.exemplar(livro["id"])["id"])
    r = f.reservar(f.usuario()["id"], livro["id"])
    novo = f.exemplar(livro["id"])
    assert novo["estado"] == "reservado"
    assert client.get(f"/reservas/{r['id']}").json()["exemplar_id"] == novo["id"]


# ------------------------------------------------------------------ Regra 7
def test_atraso_superior_a_60_dias_baixa_exemplar(client, f):
    livro = f.livro()
    ex = f.exemplar(livro["id"])
    u = f.usuario("professor")
    emp = f.emprestar(u["id"], ex["id"])
    r = f.reservar(f.usuario()["id"], livro["id"])
    clock.avancar(days=30 + 61)
    dev = f.devolver(emp["id"])
    assert dev["multa"]["valor"] == 50.0 and dev["multa"]["estado"] == "aberta"
    assert client.get(f"/exemplares/{ex['id']}").json()["estado"] == "baixado"
    assert client.get(f"/reservas/{r['id']}").json()["estado"] == "cancelada"
    usuario = client.get(f"/usuarios/{u['id']}").json()
    assert usuario["situacao"] == "suspenso"


def test_atraso_de_60_dias_nao_baixa(client, f):
    u = f.usuario("visitante")
    ex = f.exemplar(f.livro()["id"])
    emp = f.emprestar(u["id"], ex["id"])
    clock.avancar(days=3 + 60)
    dev = f.devolver(emp["id"])
    assert dev["multa"]["valor"] == 20.0
    assert client.get(f"/exemplares/{ex['id']}").json()["estado"] == "disponivel"


# ---------------------------------------------------------------- Relatorios
def test_relatorios(client, f):
    l1, l2 = f.livro(area="Computacao"), f.livro(area="Direito")
    e1, e2, e3 = f.exemplar(l1["id"]), f.exemplar(l1["id"]), f.exemplar(l2["id"])
    a, b = f.usuario(), f.usuario()
    emp1 = f.emprestar(a["id"], e1["id"])
    f.emprestar(b["id"], e2["id"])
    clock.avancar(days=10)
    f.devolver(emp1["id"])  # 3 dias de atraso para A; B segue atrasado

    r = client.get("/relatorios/livros-mais-emprestados?inicio=2026-03-01&fim=2026-03-31").json()
    assert r[0]["livro_id"] == l1["id"] and r[0]["total_emprestimos"] == 2
    assert client.get("/relatorios/livros-mais-emprestados?inicio=2026-04-01&fim=2026-04-30").json() == []
    assert client.get("/relatorios/livros-mais-emprestados?inicio=2026-04-01&fim=2026-03-01").status_code == 422
    assert client.get("/relatorios/livros-mais-emprestados").status_code == 422

    r = client.get("/relatorios/usuarios-mais-atrasos").json()
    assert {x["usuario_id"] for x in r} == {a["id"], b["id"]}
    assert all(x["quantidade_atrasos"] == 1 and x["total_dias_atraso"] == 3 for x in r)

    r = {x["area_conhecimento"]: x for x in client.get("/relatorios/ocupacao-acervo").json()}
    assert r["Computacao"]["total_exemplares"] == 2 and r["Computacao"]["taxa_ocupacao"] == 50.0
    assert r["Direito"]["taxa_ocupacao"] == 0.0


def test_listar_emprestimos_por_usuario(client, f):
    u = f.usuario()
    livro = f.livro()
    f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
    f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
    assert len(client.get(f"/usuarios/{u['id']}/emprestimos").json()) == 2
    assert len(client.get(f"/emprestimos?usuario_id={u['id']}").json()) == 2
    assert client.get("/usuarios/999/emprestimos").status_code == 404
