from datetime import date, timedelta

import pytest


# ====================================================================== CRUD e validacao
def test_crud_usuario(client, f):
    u = f.usuario("professor")
    assert u["situacao"] == "ativo"
    assert client.get(f"/usuarios/{u['id']}").status_code == 200
    r = client.patch(f"/usuarios/{u['id']}", json={"nome": "Novo Nome"})
    assert r.status_code == 200 and r.json()["nome"] == "Novo Nome"
    assert client.delete(f"/usuarios/{u['id']}").status_code == 204
    assert client.get(f"/usuarios/{u['id']}").status_code == 404


@pytest.mark.parametrize("payload", [
    {"nome": "A", "email": "invalido", "matricula": "M1", "categoria": "aluno"},
    {"nome": "A", "email": "a@b.com", "matricula": "M001", "categoria": "reitor"},
    {"nome": "", "email": "a@b.com", "matricula": "M001", "categoria": "aluno"},
    {"nome": "A", "email": "a@b.com", "matricula": "M001", "categoria": "aluno", "extra": 1},
])
def test_usuario_invalido(client, payload):
    assert client.post("/usuarios", json=payload).status_code == 422


def test_usuario_duplicado(client, f):
    u = f.usuario()
    r = client.post("/usuarios", json={"nome": "X", "email": u["email"], "matricula": "OUTRA1", "categoria": "aluno"})
    assert r.status_code == 409


def test_livro_validacao_isbn_e_ano(client, f):
    base = {"titulo": "T", "autor": "A", "ano": 2000, "area_conhecimento": "X"}
    assert client.post("/livros", json={**base, "isbn": "9780306406158"}).status_code == 422  # DV errado
    assert client.post("/livros", json={**base, "isbn": "0-306-40615-2", "ano": 3000}).status_code == 422
    r = client.post("/livros", json={**base, "isbn": "978-0-306-40615-7"})
    assert r.status_code == 201 and r.json()["isbn"] == "9780306406157"
    assert client.post("/livros", json={**base, "isbn": "9780306406157"}).status_code == 409


def test_exemplar_estado_sistemico_nao_pode_ser_definido(client, f):
    livro = f.livro()
    ex = f.exemplar(livro["id"])
    assert client.patch(f"/exemplares/{ex['id']}", json={"estado": "emprestado"}).status_code == 422
    assert client.post("/exemplares", json={"livro_id": 999, "codigo_tombo": "Z1"}).status_code == 404


def test_remocao_bloqueada_com_historico(client, f):
    u, livro = f.usuario(), f.livro()
    ex = f.exemplar(livro["id"])
    f.emprestar(u["id"], ex["id"])
    assert client.delete(f"/usuarios/{u['id']}").status_code == 409
    assert client.delete(f"/livros/{livro['id']}").status_code == 409
    assert client.delete(f"/exemplares/{ex['id']}").status_code == 409


# ====================================================================== parametros por categoria
@pytest.mark.parametrize("categoria,prazo", [("aluno", 7), ("professor", 30), ("visitante", 3)])
def test_prazo_por_categoria(client, f, relogio, categoria, prazo):
    u, livro = f.usuario(categoria), f.livro()
    emp = f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
    assert emp["data_prevista"] == str(relogio.atual.date() + timedelta(days=prazo))
    assert emp["estado"] == "ativo" and emp["numero_renovacoes"] == 0


@pytest.mark.parametrize("categoria,limite", [("aluno", 3), ("professor", 8), ("visitante", 1)])
def test_limite_de_exemplares(client, f, categoria, limite):
    u, livro = f.usuario(categoria), f.livro()
    for _ in range(limite):
        f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
    r = f.emprestar(u["id"], f.exemplar(livro["id"])["id"], esperado=409)
    assert r["detail"]["codigo"] == "LIMITE_EXEMPLARES"


@pytest.mark.parametrize("categoria,renovacoes", [("aluno", 2), ("professor", 4), ("visitante", 0)])
def test_limite_de_renovacoes(client, f, categoria, renovacoes):
    u, livro = f.usuario(categoria), f.livro()
    emp = f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
    for i in range(renovacoes):
        r = client.post(f"/emprestimos/{emp['id']}/renovacao")
        assert r.status_code == 200 and r.json()["numero_renovacoes"] == i + 1
    r = client.post(f"/emprestimos/{emp['id']}/renovacao")
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "LIMITE_RENOVACOES"


@pytest.mark.parametrize("categoria,dias,esperado", [
    ("aluno", 5, "5.00"), ("aluno", 40, "30.00"),          # R$1/dia, teto 30
    ("professor", 10, "5.00"), ("professor", 59, "29.50"),  # R$0,50/dia, teto 50
    ("visitante", 4, "8.00"), ("visitante", 15, "20.00"),   # R$2/dia, teto 20
])
def test_valor_da_multa(client, f, relogio, categoria, dias, esperado):
    u, livro = f.usuario(categoria), f.livro()
    emp = f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
    prevista = date.fromisoformat(emp["data_prevista"])
    relogio.atual = relogio.atual.replace(year=prevista.year, month=prevista.month, day=prevista.day)
    relogio.avancar(dias=dias)
    dev = f.devolver(emp["id"])
    assert dev["dias_atraso"] == dias
    assert dev["multa"]["valor"] == esperado
    assert dev["multa"]["estado"] == "aberta"


# ====================================================================== regra 1
def test_emprestimo_negado_com_multa_aberta_e_liberado_apos_pagamento(client, f, relogio):
    u, livro = f.usuario("aluno"), f.livro()
    emp = f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
    relogio.avancar(dias=9)  # 2 dias de atraso
    multa = f.devolver(emp["id"])["multa"]
    ex2 = f.exemplar(livro["id"])
    assert f.emprestar(u["id"], ex2["id"], esperado=409)["detail"]["codigo"] == "MULTA_ABERTA"

    assert client.post(f"/multas/{multa['id']}/pagamento", json={"valor": "1.00"}).status_code == 422
    r = client.post(f"/multas/{multa['id']}/pagamento", json={"valor": "2.00"})
    assert r.status_code == 200 and r.json()["estado"] == "paga"
    assert client.post(f"/multas/{multa['id']}/pagamento").status_code == 409
    f.emprestar(u["id"], ex2["id"])


def test_multa_nao_pode_ser_paga_antes_da_devolucao(client, f, relogio):
    u, livro = f.usuario(), f.livro()
    emp = f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
    relogio.avancar(dias=10)
    multas = client.get(f"/usuarios/{u['id']}/multas").json()
    assert len(multas) == 1 and multas[0]["valor"] == "3.00" and multas[0]["estado"] == "aberta"
    r = client.post(f"/multas/{multas[0]['id']}/pagamento")
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "MULTA_EM_APURACAO"
    assert client.get(f"/emprestimos/{emp['id']}").json()["estado"] == "atrasado"


def test_emprestimo_negado_a_usuario_suspenso(client, f):
    u, livro = f.usuario(situacao="suspenso"), f.livro()
    r = f.emprestar(u["id"], f.exemplar(livro["id"])["id"], esperado=409)
    assert r["detail"]["codigo"] == "USUARIO_SUSPENSO"


# ====================================================================== regra 2
def test_suspensao_automatica_por_atraso_superior_a_15_dias(client, f, relogio):
    u, livro = f.usuario("aluno"), f.livro()
    emp = f.emprestar(u["id"], f.exemplar(livro["id"])["id"])

    relogio.avancar(dias=7 + 15)  # exatamente 15 dias: ainda nao suspende
    assert client.get(f"/usuarios/{u['id']}").json()["situacao"] == "ativo"

    relogio.avancar(dias=1)  # 16 dias de atraso
    assert client.get(f"/usuarios/{u['id']}").json()["situacao"] == "suspenso"

    relogio.avancar(dias=4)  # devolve com 20 dias de atraso -> 40 dias de suspensao
    hoje = relogio.atual.date()
    f.devolver(emp["id"])
    usr = client.get(f"/usuarios/{u['id']}").json()
    assert usr["situacao"] == "suspenso"
    assert usr["suspenso_ate"] == str(hoje + timedelta(days=40))

    relogio.avancar(dias=39)
    assert client.get(f"/usuarios/{u['id']}").json()["situacao"] == "suspenso"
    relogio.avancar(dias=1)
    assert client.get(f"/usuarios/{u['id']}").json()["situacao"] == "ativo"


# ====================================================================== regra 3
def test_renovacao_negada_com_fila_de_reserva(client, f):
    u1, u2, livro = f.usuario(), f.usuario(), f.livro()
    emp = f.emprestar(u1["id"], f.exemplar(livro["id"])["id"])
    f.reservar(u2["id"], livro["id"])
    r = client.post(f"/emprestimos/{emp['id']}/renovacao")
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "FILA_RESERVA"


def test_renovacao_negada_se_atrasado(client, f, relogio):
    u, livro = f.usuario(), f.livro()
    emp = f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
    relogio.avancar(dias=8)
    r = client.post(f"/emprestimos/{emp['id']}/renovacao")
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "EMPRESTIMO_ATRASADO"


def test_renovacao_estende_prazo(client, f, relogio):
    u, livro = f.usuario("professor"), f.livro()
    emp = f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
    relogio.avancar(dias=10)
    r = client.post(f"/emprestimos/{emp['id']}/renovacao").json()
    assert r["data_prevista"] == str(relogio.atual.date() + timedelta(days=30))


# ====================================================================== regra 4
def test_fila_de_reserva_e_expiracao_48h(client, f, relogio):
    dono, a, b, livro = f.usuario(), f.usuario(), f.usuario(), f.livro()
    ex = f.exemplar(livro["id"])
    emp = f.emprestar(dono["id"], ex["id"])

    assert f.reservar(dono["id"], livro["id"], esperado=409)["detail"]["codigo"] == "LIVRO_JA_EMPRESTADO"
    ra = f.reservar(a["id"], livro["id"])
    rb = f.reservar(b["id"], livro["id"])
    assert (ra["posicao_fila"], rb["posicao_fila"]) == (1, 2)
    assert f.reservar(a["id"], livro["id"], esperado=409)["detail"]["codigo"] == "RESERVA_DUPLICADA"

    f.devolver(emp["id"])
    ra = client.get(f"/reservas/{ra['id']}").json()
    assert ra["estado"] == "disponivel" and ra["exemplar_id"] == ex["id"]
    assert client.get(f"/exemplares/{ex['id']}").json()["estado"] == "reservado"
    # B nao pode pegar o exemplar separado para A
    assert f.emprestar(b["id"], ex["id"], esperado=409)["detail"]["codigo"] == "EXEMPLAR_RESERVADO"

    relogio.avancar(horas=48)
    assert client.get(f"/reservas/{ra['id']}").json()["estado"] == "expirada"
    rb = client.get(f"/reservas/{rb['id']}").json()
    assert rb["estado"] == "disponivel" and rb["posicao_fila"] == 1

    f.emprestar(b["id"], ex["id"])
    assert client.get(f"/reservas/{rb['id']}").json()["estado"] == "atendida"
    assert client.get(f"/livros/{livro['id']}/reservas").json() == []


def test_reserva_dentro_do_prazo_permite_retirada(client, f, relogio):
    dono, a, livro = f.usuario(), f.usuario(), f.livro()
    ex = f.exemplar(livro["id"])
    emp = f.emprestar(dono["id"], ex["id"])
    f.reservar(a["id"], livro["id"])
    f.devolver(emp["id"])
    relogio.avancar(horas=47)
    f.emprestar(a["id"], ex["id"])


def test_cancelar_reserva_disponivel_passa_ao_proximo(client, f):
    dono, a, b, livro = f.usuario(), f.usuario(), f.usuario(), f.livro()
    ex = f.exemplar(livro["id"])
    emp = f.emprestar(dono["id"], ex["id"])
    ra, rb = f.reservar(a["id"], livro["id"]), f.reservar(b["id"], livro["id"])
    f.devolver(emp["id"])
    r = client.post(f"/reservas/{ra['id']}/cancelamento")
    assert r.status_code == 200 and r.json()["estado"] == "cancelada"
    assert client.get(f"/reservas/{rb['id']}").json()["estado"] == "disponivel"
    assert client.post(f"/reservas/{ra['id']}/cancelamento").status_code == 409


def test_reserva_negada_com_exemplar_disponivel(client, f):
    u, livro = f.usuario(), f.livro()
    f.exemplar(livro["id"])
    assert f.reservar(u["id"], livro["id"], esperado=409)["detail"]["codigo"] == "EXEMPLAR_DISPONIVEL"


# ====================================================================== regra 5
@pytest.mark.parametrize("dias,estado,valor", [(1, "perdoada", "0.50"), (2, "perdoada", "1.00"), (3, "aberta", "1.50")])
def test_perdao_de_multa_de_professor(client, f, relogio, dias, estado, valor):
    u, livro = f.usuario("professor"), f.livro()
    emp = f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
    relogio.avancar(dias=30 + dias)
    multa = f.devolver(emp["id"])["multa"]
    assert (multa["estado"], multa["valor"]) == (estado, valor)


def test_aluno_com_1_dia_nao_tem_perdao(client, f, relogio):
    u, livro = f.usuario("aluno"), f.livro()
    emp = f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
    relogio.avancar(dias=8)
    assert f.devolver(emp["id"])["multa"]["estado"] == "aberta"


def test_devolucao_no_prazo_sem_multa(client, f, relogio):
    u, livro = f.usuario(), f.livro()
    emp = f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
    relogio.avancar(dias=7)
    dev = f.devolver(emp["id"])
    assert dev["multa"] is None and dev["dias_atraso"] == 0


# ====================================================================== regra 6
def test_exemplar_em_reparo_ou_baixado_nao_emprestado_nem_reservado(client, f):
    u, livro = f.usuario(), f.livro()
    ex = f.exemplar(livro["id"], estado="em_reparo")
    assert f.emprestar(u["id"], ex["id"], esperado=409)["detail"]["codigo"] == "EXEMPLAR_INDISPONIVEL"
    assert f.reservar(u["id"], livro["id"], esperado=409)["detail"]["codigo"] == "SEM_EXEMPLAR_RESERVAVEL"
    client.patch(f"/exemplares/{ex['id']}", json={"estado": "baixado"})
    assert f.emprestar(u["id"], ex["id"], esperado=409)["detail"]["codigo"] == "EXEMPLAR_INDISPONIVEL"
    assert client.patch(f"/exemplares/{ex['id']}", json={"estado": "disponivel"}).status_code == 409


def test_baixa_do_ultimo_exemplar_cancela_reservas(client, f):
    dono, a, livro = f.usuario(), f.usuario(), f.livro()
    ex = f.exemplar(livro["id"])
    emp = f.emprestar(dono["id"], ex["id"])
    ra = f.reservar(a["id"], livro["id"])
    f.devolver(emp["id"])  # exemplar fica reservado para A
    r = client.patch(f"/exemplares/{ex['id']}", json={"estado": "baixado"})
    assert r.status_code == 200
    assert client.get(f"/reservas/{ra['id']}").json()["estado"] == "cancelada"


def test_baixa_de_exemplar_nao_ultimo_mantem_reservas(client, f):
    d1, d2, a, livro = f.usuario(), f.usuario(), f.usuario(), f.livro()
    e1, e2 = f.exemplar(livro["id"]), f.exemplar(livro["id"])
    emp1 = f.emprestar(d1["id"], e1["id"])
    f.emprestar(d2["id"], e2["id"])
    ra = f.reservar(a["id"], livro["id"])
    f.devolver(emp1["id"])  # e1 separado para A
    client.patch(f"/exemplares/{e1['id']}", json={"estado": "baixado"})
    ra = client.get(f"/reservas/{ra['id']}").json()
    assert ra["estado"] == "aguardando"  # e2 ainda circula: reserva volta a aguardar


def test_exemplar_volta_do_reparo_atende_fila(client, f):
    dono, a, livro = f.usuario(), f.usuario(), f.livro()
    e1, e2 = f.exemplar(livro["id"]), f.exemplar(livro["id"], estado="em_reparo")
    f.emprestar(dono["id"], e1["id"])
    ra = f.reservar(a["id"], livro["id"])
    client.patch(f"/exemplares/{e2['id']}", json={"estado": "disponivel"})
    assert client.get(f"/exemplares/{e2['id']}").json()["estado"] == "reservado"
    assert client.get(f"/reservas/{ra['id']}").json()["estado"] == "disponivel"


# ====================================================================== regra 7
@pytest.mark.parametrize("categoria,prazo,teto", [("aluno", 7, "30.00"), ("professor", 30, "50.00"), ("visitante", 3, "20.00")])
def test_devolucao_com_mais_de_60_dias_baixa_exemplar(client, f, relogio, categoria, prazo, teto):
    u, a, livro = f.usuario(categoria), f.usuario(), f.livro()
    ex = f.exemplar(livro["id"])
    emp = f.emprestar(u["id"], ex["id"])
    ra = f.reservar(a["id"], livro["id"])
    relogio.avancar(dias=prazo + 61)
    dev = f.devolver(emp["id"])
    assert dev["multa"]["valor"] == teto and dev["multa"]["estado"] == "aberta"
    assert client.get(f"/exemplares/{ex['id']}").json()["estado"] == "baixado"
    assert client.get(f"/reservas/{ra['id']}").json()["estado"] == "cancelada"


def test_devolucao_com_exatos_60_dias_nao_baixa(client, f, relogio):
    u, livro = f.usuario("professor"), f.livro()
    ex = f.exemplar(livro["id"])
    emp = f.emprestar(u["id"], ex["id"])
    relogio.avancar(dias=30 + 60)
    dev = f.devolver(emp["id"])
    assert dev["multa"]["valor"] == "30.00"
    assert client.get(f"/exemplares/{ex['id']}").json()["estado"] == "disponivel"


# ====================================================================== relatorios
def test_relatorios(client, f, relogio):
    u1, u2 = f.usuario("professor"), f.usuario("professor")
    l1, l2 = f.livro("Computacao"), f.livro("Direito")
    e1, e2, e3 = f.exemplar(l1["id"]), f.exemplar(l1["id"]), f.exemplar(l2["id"])
    f.exemplar(l2["id"])
    inicio = relogio.atual.date()

    a = f.emprestar(u1["id"], e1["id"])
    f.emprestar(u2["id"], e2["id"])
    f.emprestar(u2["id"], e3["id"])
    relogio.avancar(dias=35)  # todos 5 dias atrasados
    f.devolver(a["id"])

    r = client.get("/relatorios/livros-mais-emprestados", params={"inicio": str(inicio), "fim": str(inicio)}).json()
    assert [(x["livro_id"], x["total_emprestimos"]) for x in r] == [(l1["id"], 2), (l2["id"], 1)]
    assert client.get("/relatorios/livros-mais-emprestados",
                      params={"inicio": "2026-02-01", "fim": "2026-01-01"}).status_code == 422

    r = client.get("/relatorios/usuarios-mais-atrasos").json()
    assert [(x["usuario_id"], x["total_atrasos"], x["total_dias_atraso"]) for x in r] == [
        (u2["id"], 2, 10), (u1["id"], 1, 5)
    ]

    r = {x["area_conhecimento"]: x for x in client.get("/relatorios/ocupacao-acervo").json()}
    assert r["Computacao"]["emprestados"] == 1 and r["Computacao"]["taxa_ocupacao"] == 0.5
    assert r["Direito"]["emprestados"] == 1 and r["Direito"]["taxa_ocupacao"] == 0.5


def test_listagens_por_usuario(client, f):
    u, livro = f.usuario(), f.livro()
    f.emprestar(u["id"], f.exemplar(livro["id"])["id"])
    assert len(client.get(f"/usuarios/{u['id']}/emprestimos").json()) == 1
    assert len(client.get("/emprestimos", params={"usuario_id": u["id"]}).json()) == 1
    assert client.get("/emprestimos").status_code == 422
    assert client.get("/usuarios/999/emprestimos").status_code == 404
