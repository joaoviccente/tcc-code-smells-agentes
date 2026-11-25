import pytest

# (categoria, prazo, dias de atraso, valor esperado, estado esperado)
CASOS = [
    ("aluno", 7, 1, "1.00", "aberta"),
    ("aluno", 7, 5, "5.00", "aberta"),
    ("aluno", 7, 30, "30.00", "aberta"),
    ("aluno", 7, 45, "30.00", "aberta"),        # teto R$ 30,00
    ("professor", 30, 1, "0.50", "perdoada"),   # ate 2 dias: perdoada
    ("professor", 30, 2, "1.00", "perdoada"),
    ("professor", 30, 3, "1.50", "aberta"),
    ("professor", 30, 60, "30.00", "aberta"),
    ("visitante", 3, 3, "6.00", "aberta"),
    ("visitante", 3, 10, "20.00", "aberta"),
    ("visitante", 3, 14, "20.00", "aberta"),    # teto R$ 20,00
]


@pytest.mark.parametrize("categoria,prazo,atraso,valor,estado", CASOS)
def test_valor_da_multa(api, tempo, categoria, prazo, atraso, valor, estado):
    u = api.usuario(categoria)
    emp = api.emprestar(u["id"], api.exemplar(api.livro()["id"])["id"])
    tempo.avancar(dias=prazo + atraso)
    api.devolver(emp["id"])
    [multa] = api.get(f"/usuarios/{u['id']}/multas")
    assert multa["valor"] == valor
    assert multa["estado"] == estado
    assert multa["dias_atraso"] == atraso


def test_multa_acumula_durante_atraso_e_bloqueia_emprestimo(api, tempo):
    u = api.usuario("aluno")
    livro = api.livro()
    emp = api.emprestar(u["id"], api.exemplar(livro["id"])["id"])
    outro = api.exemplar(livro["id"])
    tempo.avancar(dias=10)  # 3 dias de atraso
    [multa] = api.get(f"/usuarios/{u['id']}/multas")
    assert (multa["valor"], multa["estado"]) == ("3.00", "aberta")
    tempo.avancar(dias=2)
    assert api.get(f"/multas/{multa['id']}")["valor"] == "5.00"

    r = api.c.post("/emprestimos", json={"usuario_id": u["id"], "exemplar_id": outro["id"]})
    assert r.status_code == 409 and "multa" in r.json()["detail"]
    # multa ainda em acumulo nao pode ser paga
    assert api.c.post(f"/multas/{multa['id']}/pagamento").status_code == 409

    api.devolver(emp["id"])
    r = api.c.post(f"/multas/{multa['id']}/pagamento")
    assert r.status_code == 200 and r.json()["estado"] == "paga" and r.json()["valor"] == "5.00"
    assert api.c.post(f"/multas/{multa['id']}/pagamento").status_code == 409
    assert api.c.post("/multas/999/pagamento").status_code == 404
    api.emprestar(u["id"], outro["id"])


def test_atraso_de_15_dias_nao_suspende(api, tempo):
    u = api.usuario("aluno")
    emp = api.emprestar(u["id"], api.exemplar(api.livro()["id"])["id"])
    tempo.avancar(dias=7 + 15)
    assert api.get(f"/usuarios/{u['id']}")["situacao"] == "ativo"
    api.devolver(emp["id"])
    assert api.get(f"/usuarios/{u['id']}")["situacao"] == "ativo"


def test_atraso_superior_a_15_dias_suspende_pelo_dobro(api, tempo):
    u = api.usuario("aluno")
    emp = api.emprestar(u["id"], api.exemplar(api.livro()["id"])["id"])
    tempo.avancar(dias=7 + 16)  # 16 dias de atraso -> suspensao automatica, mesmo sem devolver
    assert api.get(f"/usuarios/{u['id']}")["situacao"] == "suspenso"
    tempo.avancar(dias=4)       # devolve com 20 dias de atraso
    api.devolver(emp["id"])
    usuario = api.get(f"/usuarios/{u['id']}")
    assert usuario["situacao"] == "suspenso"
    assert usuario["suspenso_ate"] == "2026-05-08"  # devolucao em 29/03 + 40 dias

    # paga a multa para isolar o efeito da suspensao
    [multa] = api.get(f"/usuarios/{u['id']}/multas")
    api.c.post(f"/multas/{multa['id']}/pagamento")
    ex = api.exemplar(api.livro()["id"])
    tempo.avancar(dias=39)
    assert api.get(f"/usuarios/{u['id']}")["situacao"] == "suspenso"
    api.emprestar(u["id"], ex["id"], esperado=409)
    tempo.avancar(dias=1)
    assert api.get(f"/usuarios/{u['id']}")["situacao"] == "ativo"
    api.emprestar(u["id"], ex["id"])


def test_atraso_superior_a_60_dias_baixa_exemplar_e_cobra_teto(api, tempo):
    u = api.usuario("professor")
    livro = api.livro()
    ex = api.exemplar(livro["id"])
    emp = api.emprestar(u["id"], ex["id"])
    tempo.avancar(dias=30 + 61)  # pelo calculo diario seria R$ 30,50; regra 7 cobra o teto (R$ 50,00)
    api.devolver(emp["id"])
    assert api.get(f"/exemplares/{ex['id']}")["estado"] == "baixado"
    [multa] = api.get(f"/usuarios/{u['id']}/multas")
    assert (multa["valor"], multa["estado"]) == ("50.00", "aberta")
    assert api.get(f"/usuarios/{u['id']}")["suspenso_ate"] == "2026-10-01"  # 01/06 + 122 dias


def test_atraso_de_60_dias_nao_baixa(api, tempo):
    u = api.usuario("professor")
    ex = api.exemplar(api.livro()["id"])
    emp = api.emprestar(u["id"], ex["id"])
    tempo.avancar(dias=30 + 60)
    api.devolver(emp["id"])
    assert api.get(f"/exemplares/{ex['id']}")["estado"] == "disponivel"
    assert api.get(f"/usuarios/{u['id']}/multas")[0]["valor"] == "30.00"


def test_listar_multas_por_estado(api, tempo):
    u = api.usuario("professor")
    livro = api.livro()
    e1 = api.emprestar(u["id"], api.exemplar(livro["id"])["id"])
    e2 = api.emprestar(u["id"], api.exemplar(livro["id"])["id"])
    tempo.avancar(dias=31)
    api.devolver(e1["id"])
    tempo.avancar(dias=4)
    api.devolver(e2["id"])
    assert [m["valor"] for m in api.get(f"/usuarios/{u['id']}/multas?estado=perdoada")] == ["0.50"]
    assert [m["valor"] for m in api.get(f"/usuarios/{u['id']}/multas?estado=aberta")] == ["2.50"]
