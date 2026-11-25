from datetime import date, timedelta

import pytest

from tests.conftest import INICIO


# ---------------------------------------------------------------- CRUD e validacao
def test_validacao_e_unicidade_de_usuario(client, fab):
    assert client.post("/usuarios", json={"nome": "A", "email": "invalido", "matricula": "1",
                                          "categoria": "aluno"}).status_code == 422
    assert client.post("/usuarios", json={"nome": "A", "email": "a@x.br", "matricula": "1",
                                          "categoria": "reitor"}).status_code == 422
    assert client.post("/usuarios", json={"nome": "A", "email": "a@x.br", "matricula": "1",
                                          "categoria": "aluno", "extra": 1}).status_code == 422
    u = fab.usuario()
    r = client.post("/usuarios", json={"nome": "B", "email": "outro@x.br", "matricula": u["matricula"],
                                       "categoria": "aluno"})
    assert r.status_code == 409
    assert client.get("/usuarios/9999").status_code == 404
    r = client.patch(f"/usuarios/{u['id']}", json={"categoria": "professor"})
    assert r.status_code == 200 and r.json()["categoria"] == "professor"
    assert client.delete(f"/usuarios/{u['id']}").status_code == 204
    assert client.get(f"/usuarios/{u['id']}").status_code == 404


def test_validacao_de_livro_e_exemplar(client, fab):
    base = {"titulo": "T", "autor": "A", "ano": 2020, "area_conhecimento": "X"}
    assert client.post("/livros", json={**base, "isbn": "9780000000000"}).status_code == 422  # DV errado
    assert client.post("/livros", json={**base, "isbn": "978-85-333-0227-3", "ano": 3000}).status_code == 422
    r = client.post("/livros", json={**base, "isbn": "978-85-333-0227-3"})
    assert r.status_code == 201 and r.json()["isbn"] == "9788533302273"
    assert client.post("/livros", json={**base, "isbn": "9788533302273"}).status_code == 409
    assert client.post("/livros", json={**base, "isbn": "0-306-40615-2"}).status_code == 201  # ISBN-10

    livro = r.json()
    ex = fab.exemplar(livro["id"])
    assert client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": ex["codigo_tombo"]}).status_code == 409
    assert client.post("/exemplares", json={"livro_id": 999, "codigo_tombo": "Z"}).status_code == 404
    assert client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "Z",
                                            "estado": "emprestado"}).status_code == 422
    assert client.delete(f"/livros/{livro['id']}").status_code == 409  # possui exemplares


# ---------------------------------------------------------------- regras por categoria
@pytest.mark.parametrize("categoria,prazo,limite", [("aluno", 7, 3), ("professor", 30, 8), ("visitante", 3, 1)])
def test_prazo_e_limite_por_categoria(client, fab, categoria, prazo, limite):
    u = fab.usuario(categoria)
    livro = fab.livro()
    exs = [fab.exemplar(livro["id"]) for _ in range(limite + 1)]
    for ex in exs[:limite]:
        emp = fab.emprestimo(u["id"], ex["id"])
        assert emp["data_prevista"] == str(INICIO.date() + timedelta(days=prazo))
        assert emp["categoria_usuario"] == categoria
    r = client.post("/emprestimos", json={"usuario_id": u["id"], "exemplar_id": exs[-1]["id"]})
    assert r.status_code == 409 and "limite" in r.json()["detail"]


@pytest.mark.parametrize("categoria,dias,valor,estado", [
    ("aluno", 5, 5.00, "aberta"),
    ("aluno", 45, 30.00, "aberta"),        # teto
    ("professor", 1, 0.50, "perdoada"),
    ("professor", 2, 1.00, "perdoada"),    # ate 2 dias: perdoada
    ("professor", 3, 1.50, "aberta"),
    ("professor", 59, 29.50, "aberta"),
    ("visitante", 4, 8.00, "aberta"),
    ("visitante", 15, 20.00, "aberta"),    # teto
])
def test_multa_por_categoria(client, fab, tempo, categoria, dias, valor, estado):
    u = fab.usuario(categoria)
    ex = fab.exemplar(fab.livro()["id"])
    emp = fab.emprestimo(u["id"], ex["id"])
    prazo = (date.fromisoformat(emp["data_prevista"]) - INICIO.date()).days
    tempo.avancar(dias=prazo + dias)
    r = client.post(f"/emprestimos/{emp['id']}/devolucao")
    assert r.status_code == 200
    multa = r.json()["multa"]
    assert multa["dias_atraso"] == dias and multa["valor"] == valor and multa["estado"] == estado


def test_devolucao_no_prazo_nao_gera_multa(client, fab, tempo):
    u = fab.usuario()
    emp = fab.emprestimo(u["id"], fab.exemplar(fab.livro()["id"])["id"])
    tempo.avancar(dias=7)
    r = client.post(f"/emprestimos/{emp['id']}/devolucao").json()
    assert r["multa"] is None and r["estado"] == "devolvido" and r["dias_atraso"] == 0
    assert client.post(f"/emprestimos/{emp['id']}/devolucao").status_code == 409


# ---------------------------------------------------------------- regra 1 e pagamento
def test_multa_aberta_bloqueia_emprestimo_ate_pagamento(client, fab, tempo):
    u = fab.usuario()
    livro = fab.livro()
    ex1, ex2 = fab.exemplar(livro["id"]), fab.exemplar(livro["id"])
    emp = fab.emprestimo(u["id"], ex1["id"])
    tempo.avancar(dias=10)  # 3 dias de atraso

    emp_atual = client.get(f"/emprestimos/{emp['id']}").json()
    assert emp_atual["estado"] == "atrasado" and emp_atual["multa"]["valor"] == 3.0
    multa_id = emp_atual["multa"]["id"]
    assert client.post(f"/multas/{multa_id}/pagamento").status_code == 409  # ainda acumulando
    assert client.post("/emprestimos", json={"usuario_id": u["id"], "exemplar_id": ex2["id"]}).status_code == 409

    client.post(f"/emprestimos/{emp['id']}/devolucao")
    assert client.post("/emprestimos", json={"usuario_id": u["id"], "exemplar_id": ex2["id"]}).status_code == 409
    assert client.post(f"/multas/{multa_id}/pagamento", json={"valor": 2.5}).status_code == 422
    r = client.post(f"/multas/{multa_id}/pagamento", json={"valor": 3.0})
    assert r.status_code == 200 and r.json()["estado"] == "paga"
    assert client.post(f"/multas/{multa_id}/pagamento").status_code == 409
    assert [m["estado"] for m in client.get(f"/usuarios/{u['id']}/multas").json()] == ["paga"]
    fab.emprestimo(u["id"], ex2["id"])


def test_professor_com_ate_2_dias_de_atraso_nao_fica_bloqueado(client, fab, tempo):
    u = fab.usuario("professor")
    livro = fab.livro()
    ex1, ex2 = fab.exemplar(livro["id"]), fab.exemplar(livro["id"])
    emp = fab.emprestimo(u["id"], ex1["id"])
    tempo.avancar(dias=32)
    fab.emprestimo(u["id"], ex2["id"])
    tempo.avancar(dias=1)  # 3 dias de atraso: multa passa a aberta
    assert client.get(f"/emprestimos/{emp['id']}").json()["multa"]["estado"] == "aberta"


# ---------------------------------------------------------------- regra 2
def test_suspensao_por_atraso_superior_a_15_dias(client, fab, tempo):
    u = fab.usuario()
    livro = fab.livro()
    ex1, ex2 = fab.exemplar(livro["id"]), fab.exemplar(livro["id"])
    emp = fab.emprestimo(u["id"], ex1["id"])

    tempo.avancar(dias=7 + 15)  # 15 dias de atraso: ainda nao suspende
    assert client.get(f"/usuarios/{u['id']}").json()["situacao"] == "ativo"
    tempo.avancar(dias=1)       # 16 dias
    assert client.get(f"/usuarios/{u['id']}").json()["situacao"] == "suspenso"

    r = client.post(f"/emprestimos/{emp['id']}/devolucao").json()
    assert r["dias_atraso"] == 16 and r["multa"]["valor"] == 16.0
    usuario = client.get(f"/usuarios/{u['id']}").json()
    hoje = (INICIO + timedelta(days=23)).date()
    assert usuario["suspensao_ate"] == str(hoje + timedelta(days=32))

    client.post(f"/multas/{r['multa']['id']}/pagamento")
    tempo.avancar(dias=31)
    assert client.post("/emprestimos", json={"usuario_id": u["id"], "exemplar_id": ex2["id"]}).status_code == 409
    tempo.avancar(dias=1)
    assert client.get(f"/usuarios/{u['id']}").json()["situacao"] == "ativo"
    fab.emprestimo(u["id"], ex2["id"])


# ---------------------------------------------------------------- regra 3
def test_renovacao_limites_por_categoria(client, fab, tempo):
    aluno, visitante = fab.usuario("aluno"), fab.usuario("visitante")
    livro = fab.livro()
    emp = fab.emprestimo(aluno["id"], fab.exemplar(livro["id"])["id"])
    for i in (1, 2):
        tempo.avancar(dias=5)
        r = client.post(f"/emprestimos/{emp['id']}/renovacao")
        assert r.status_code == 200 and r.json()["renovacoes"] == i
        assert r.json()["data_prevista"] == str(tempo.atual.date() + timedelta(days=7))
    assert client.post(f"/emprestimos/{emp['id']}/renovacao").status_code == 409

    emp_v = fab.emprestimo(visitante["id"], fab.exemplar(livro["id"])["id"])
    assert client.post(f"/emprestimos/{emp_v['id']}/renovacao").status_code == 409


def test_renovacao_negada_se_atrasado_ou_com_fila(client, fab, tempo):
    a, b = fab.usuario(), fab.usuario()
    livro = fab.livro()
    emp = fab.emprestimo(a["id"], fab.exemplar(livro["id"])["id"])
    assert client.post("/reservas", json={"usuario_id": b["id"], "livro_id": livro["id"]}).status_code == 201
    r = client.post(f"/emprestimos/{emp['id']}/renovacao")
    assert r.status_code == 409 and "fila" in r.json()["detail"]

    outro = fab.livro()
    emp2 = fab.emprestimo(a["id"], fab.exemplar(outro["id"])["id"])
    tempo.avancar(dias=8)
    r = client.post(f"/emprestimos/{emp2['id']}/renovacao")
    assert r.status_code == 409 and "atrasado" in r.json()["detail"]


# ---------------------------------------------------------------- regra 4
def test_fila_de_reserva_disponibilizacao_e_expiracao(client, fab, tempo):
    dono, a, b = fab.usuario(), fab.usuario(), fab.usuario()
    livro = fab.livro()
    ex = fab.exemplar(livro["id"])
    emp = fab.emprestimo(dono["id"], ex["id"])

    ra = client.post("/reservas", json={"usuario_id": a["id"], "livro_id": livro["id"]}).json()
    tempo.avancar(horas=1)
    rb = client.post("/reservas", json={"usuario_id": b["id"], "livro_id": livro["id"]}).json()
    assert (ra["posicao"], rb["posicao"]) == (1, 2)
    assert client.post("/reservas", json={"usuario_id": a["id"], "livro_id": livro["id"]}).status_code == 409

    tempo.avancar(dias=2)
    client.post(f"/emprestimos/{emp['id']}/devolucao")
    fila = client.get(f"/livros/{livro['id']}/reservas").json()
    assert [(r["id"], r["estado"]) for r in fila] == [(ra["id"], "disponivel"), (rb["id"], "aguardando")]
    assert client.get(f"/exemplares/{ex['id']}").json()["estado"] == "reservado"
    assert client.post("/emprestimos", json={"usuario_id": b["id"], "exemplar_id": ex["id"]}).status_code == 409

    tempo.avancar(horas=48)  # exatamente 48h: ainda valida
    assert client.get(f"/reservas/{ra['id']}").json()["estado"] == "disponivel"
    tempo.avancar(horas=1)
    assert client.get(f"/reservas/{ra['id']}").json()["estado"] == "expirada"
    r_b = client.get(f"/reservas/{rb['id']}").json()
    assert r_b["estado"] == "disponivel" and r_b["posicao"] == 1

    emp_b = fab.emprestimo(b["id"], ex["id"])
    assert client.get(f"/reservas/{rb['id']}").json()["estado"] == "atendida"
    assert client.get(f"/livros/{livro['id']}/reservas").json() == []
    assert emp_b["exemplar_id"] == ex["id"]


def test_cancelar_reserva_disponivel_passa_a_vez(client, fab):
    dono, a, b = fab.usuario(), fab.usuario(), fab.usuario()
    livro = fab.livro()
    ex = fab.exemplar(livro["id"])
    emp = fab.emprestimo(dono["id"], ex["id"])
    ra = client.post("/reservas", json={"usuario_id": a["id"], "livro_id": livro["id"]}).json()
    rb = client.post("/reservas", json={"usuario_id": b["id"], "livro_id": livro["id"]}).json()
    client.post(f"/emprestimos/{emp['id']}/devolucao")
    r = client.post(f"/reservas/{ra['id']}/cancelamento")
    assert r.status_code == 200 and r.json()["estado"] == "cancelada"
    assert client.get(f"/reservas/{rb['id']}").json()["estado"] == "disponivel"
    assert client.post(f"/reservas/{ra['id']}/cancelamento").status_code == 409


def test_reserva_negada_com_exemplar_disponivel(client, fab):
    u = fab.usuario()
    livro = fab.livro()
    fab.exemplar(livro["id"])
    assert client.post("/reservas", json={"usuario_id": u["id"], "livro_id": livro["id"]}).status_code == 409


# ---------------------------------------------------------------- regra 6
def test_exemplar_em_reparo_nao_pode_ser_emprestado_nem_reservado(client, fab):
    u = fab.usuario()
    livro = fab.livro()
    ex = fab.exemplar(livro["id"], estado="em_reparo")
    assert client.post("/emprestimos", json={"usuario_id": u["id"], "exemplar_id": ex["id"]}).status_code == 409
    assert client.post("/reservas", json={"usuario_id": u["id"], "livro_id": livro["id"]}).status_code == 409
    client.patch(f"/exemplares/{ex['id']}", json={"estado": "baixado"})
    assert client.post("/emprestimos", json={"usuario_id": u["id"], "exemplar_id": ex["id"]}).status_code == 409
    assert client.patch(f"/exemplares/{ex['id']}", json={"estado": "disponivel"}).status_code == 409


def test_baixa_do_ultimo_exemplar_cancela_reservas(client, fab):
    dono, a, b = fab.usuario(), fab.usuario(), fab.usuario()
    livro = fab.livro()
    ex = fab.exemplar(livro["id"])
    emp = fab.emprestimo(dono["id"], ex["id"])
    ra = client.post("/reservas", json={"usuario_id": a["id"], "livro_id": livro["id"]}).json()
    rb = client.post("/reservas", json={"usuario_id": b["id"], "livro_id": livro["id"]}).json()
    client.post(f"/emprestimos/{emp['id']}/devolucao")  # exemplar fica reservado para A
    assert client.patch(f"/exemplares/{ex['id']}", json={"estado": "baixado"}).status_code == 200
    assert client.get(f"/reservas/{ra['id']}").json()["estado"] == "cancelada"
    assert client.get(f"/reservas/{rb['id']}").json()["estado"] == "cancelada"


def test_reparo_de_exemplar_reservado_devolve_reserva_a_fila(client, fab):
    dono, a = fab.usuario(), fab.usuario()
    livro = fab.livro()
    ex1, ex2 = fab.exemplar(livro["id"]), fab.exemplar(livro["id"])
    fab.emprestimo(dono["id"], ex2["id"])
    emp = fab.emprestimo(dono["id"], ex1["id"])
    ra = client.post("/reservas", json={"usuario_id": a["id"], "livro_id": livro["id"]}).json()
    client.post(f"/emprestimos/{emp['id']}/devolucao")
    client.patch(f"/exemplares/{ex1['id']}", json={"estado": "em_reparo"})
    r = client.get(f"/reservas/{ra['id']}").json()
    assert r["estado"] == "aguardando" and r["posicao"] == 1  # outro exemplar ainda circula
    client.patch(f"/exemplares/{ex1['id']}", json={"estado": "disponivel"})
    assert client.get(f"/reservas/{ra['id']}").json()["estado"] == "disponivel"


# ---------------------------------------------------------------- regra 7
def test_devolucao_com_mais_de_60_dias_baixa_exemplar_e_multa_no_teto(client, fab, tempo):
    prof, a = fab.usuario("professor"), fab.usuario()
    livro = fab.livro()
    ex = fab.exemplar(livro["id"])
    emp = fab.emprestimo(prof["id"], ex["id"])
    ra = client.post("/reservas", json={"usuario_id": a["id"], "livro_id": livro["id"]}).json()
    tempo.avancar(dias=30 + 61)
    assert client.get(f"/emprestimos/{emp['id']}").json()["multa"]["valor"] == 30.5  # ainda acumulando
    r = client.post(f"/emprestimos/{emp['id']}/devolucao").json()
    assert r["multa"]["valor"] == 50.0 and r["multa"]["estado"] == "aberta"
    assert client.get(f"/exemplares/{ex['id']}").json()["estado"] == "baixado"
    assert client.get(f"/reservas/{ra['id']}").json()["estado"] == "cancelada"
    assert client.get(f"/usuarios/{prof['id']}").json()["situacao"] == "suspenso"


def test_devolucao_com_60_dias_nao_baixa(client, fab, tempo):
    u = fab.usuario("aluno")
    ex = fab.exemplar(fab.livro()["id"])
    emp = fab.emprestimo(u["id"], ex["id"])
    tempo.avancar(dias=7 + 60)
    client.post(f"/emprestimos/{emp['id']}/devolucao")
    assert client.get(f"/exemplares/{ex['id']}").json()["estado"] == "disponivel"


# ---------------------------------------------------------------- relatorios
def test_relatorios(client, fab, tempo):
    a, b = fab.usuario(), fab.usuario()
    l1, l2 = fab.livro(area="Computacao"), fab.livro(area="Direito")
    e1, e2, e3 = fab.exemplar(l1["id"]), fab.exemplar(l1["id"]), fab.exemplar(l2["id"])
    emp1 = fab.emprestimo(a["id"], e1["id"])
    client.post(f"/emprestimos/{emp1['id']}/devolucao")
    fab.emprestimo(a["id"], e1["id"])
    emp3 = fab.emprestimo(b["id"], e3["id"])

    r = client.get("/relatorios/livros-mais-emprestados",
                   params={"data_inicio": str(INICIO.date()), "data_fim": str(INICIO.date())}).json()
    assert [(x["livro_id"], x["total_emprestimos"]) for x in r] == [(l1["id"], 2), (l2["id"], 1)]
    assert client.get("/relatorios/livros-mais-emprestados",
                      params={"data_inicio": "2026-02-01", "data_fim": "2026-01-01"}).status_code == 422
    assert client.get("/relatorios/livros-mais-emprestados").status_code == 422

    ocup = {x["area_conhecimento"]: x for x in client.get("/relatorios/ocupacao-acervo").json()}
    assert ocup["Computacao"]["taxa_ocupacao"] == 50.0 and ocup["Computacao"]["total_exemplares"] == 2
    assert ocup["Direito"]["taxa_ocupacao"] == 100.0

    tempo.avancar(dias=10)
    client.post(f"/emprestimos/{emp3['id']}/devolucao")
    r = client.get("/relatorios/usuarios-mais-atrasos").json()
    assert [(x["usuario_id"], x["quantidade_atrasos"], x["total_dias_atraso"]) for x in r] == \
        [(a["id"], 1, 3), (b["id"], 1, 3)]
