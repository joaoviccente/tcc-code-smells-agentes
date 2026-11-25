from datetime import datetime, timedelta

import pytest

from tests.conftest import INICIO


def _prevista(emp):
    return datetime.fromisoformat(emp["data_prevista"])


# ------------------------------------------------------------- prazos e limites por categoria
@pytest.mark.parametrize("categoria,limite,prazo", [("aluno", 3, 7), ("professor", 8, 30), ("visitante", 1, 3)])
def test_limite_e_prazo_por_categoria(fabrica, categoria, limite, prazo):
    u = fabrica.usuario(categoria)
    livro = fabrica.livro()
    exs = [fabrica.exemplar(livro["id"]) for _ in range(limite + 1)]
    for ex in exs[:limite]:
        emp = fabrica.emprestar(u["id"], ex["id"])
        assert _prevista(emp) == INICIO + timedelta(days=prazo)
    r = fabrica.emprestar(u["id"], exs[limite]["id"], esperado=409)
    assert "Limite" in r["detail"]


@pytest.mark.parametrize("categoria,renovacoes", [("aluno", 2), ("professor", 4), ("visitante", 0)])
def test_limite_de_renovacoes(client, fabrica, relogio, categoria, renovacoes):
    u = fabrica.usuario(categoria)
    ex = fabrica.exemplar(fabrica.livro()["id"])
    emp = fabrica.emprestar(u["id"], ex["id"])
    for i in range(renovacoes):
        relogio.avancar(dias=1)
        r = client.post(f"/emprestimos/{emp['id']}/renovacao")
        assert r.status_code == 200, r.text
        assert r.json()["renovacoes"] == i + 1
    r = client.post(f"/emprestimos/{emp['id']}/renovacao")
    assert r.status_code == 409


# ------------------------------------------------------------- regra 1
def test_emprestimo_negado_usuario_suspenso(client, fabrica):
    u = fabrica.usuario(situacao="suspenso")
    ex = fabrica.exemplar(fabrica.livro()["id"])
    assert "suspenso" in fabrica.emprestar(u["id"], ex["id"], esperado=409)["detail"]


def test_emprestimo_negado_com_multa_aberta_e_liberado_apos_pagamento(client, fabrica, relogio):
    u = fabrica.usuario("aluno")
    livro = fabrica.livro()
    ex1, ex2 = fabrica.exemplar(livro["id"]), fabrica.exemplar(livro["id"])
    emp = fabrica.emprestar(u["id"], ex1["id"])
    relogio.avancar(dias=7 + 3)
    fabrica.devolver(emp["id"])
    multa = fabrica.multas(u["id"])[0]
    assert multa["estado"] == "aberta" and multa["valor"] == "3.00"
    assert "multa" in fabrica.emprestar(u["id"], ex2["id"], esperado=409)["detail"]
    r = client.post(f"/multas/{multa['id']}/pagamento")
    assert r.status_code == 200 and r.json()["estado"] == "paga"
    assert client.post(f"/multas/{multa['id']}/pagamento").status_code == 409
    fabrica.emprestar(u["id"], ex2["id"])


# ------------------------------------------------------------- regra 5
@pytest.mark.parametrize("categoria,prazo,dias,valor,estado", [
    ("aluno", 7, 5, "5.00", "aberta"),
    ("aluno", 7, 30, "30.00", "aberta"),
    ("aluno", 7, 45, "30.00", "aberta"),       # teto R$ 30
    ("professor", 30, 3, "1.50", "aberta"),
    ("professor", 30, 100, "50.00", "aberta"),  # teto R$ 50
    ("professor", 30, 1, "0.50", "perdoada"),   # ate 2 dias: perdoada
    ("professor", 30, 2, "1.00", "perdoada"),
    ("visitante", 3, 4, "8.00", "aberta"),
    ("visitante", 3, 15, "20.00", "aberta"),    # teto R$ 20
])
def test_calculo_da_multa(fabrica, relogio, categoria, prazo, dias, valor, estado):
    u = fabrica.usuario(categoria)
    ex = fabrica.exemplar(fabrica.livro()["id"])
    emp = fabrica.emprestar(u["id"], ex["id"])
    relogio.avancar(dias=prazo + dias)
    fabrica.devolver(emp["id"])
    multas = fabrica.multas(u["id"])
    assert len(multas) == 1
    assert multas[0]["valor"] == valor
    assert multas[0]["estado"] == estado
    assert multas[0]["dias_atraso"] == dias


def test_multa_acumula_enquanto_emprestimo_aberto(client, fabrica, relogio):
    u = fabrica.usuario("aluno")
    ex = fabrica.exemplar(fabrica.livro()["id"])
    emp = fabrica.emprestar(u["id"], ex["id"])
    relogio.avancar(dias=9)
    assert fabrica.get(f"/emprestimos/{emp['id']}")["estado"] == "atrasado"
    assert fabrica.multas(u["id"])[0]["valor"] == "2.00"
    relogio.avancar(dias=3)
    m = fabrica.multas(u["id"])[0]
    assert m["valor"] == "5.00"
    # pagamento so apos devolucao
    assert client.post(f"/multas/{m['id']}/pagamento").status_code == 409


def test_professor_sem_multa_aberta_durante_dois_primeiros_dias(fabrica, relogio):
    u = fabrica.usuario("professor")
    livro = fabrica.livro()
    ex1, ex2 = fabrica.exemplar(livro["id"]), fabrica.exemplar(livro["id"])
    fabrica.emprestar(u["id"], ex1["id"])
    relogio.avancar(dias=32)
    assert fabrica.multas(u["id"]) == []
    fabrica.emprestar(u["id"], ex2["id"])


def test_sem_multa_se_devolvido_no_prazo(fabrica, relogio):
    u = fabrica.usuario("aluno")
    ex = fabrica.exemplar(fabrica.livro()["id"])
    emp = fabrica.emprestar(u["id"], ex["id"])
    relogio.avancar(dias=7, horas=5)  # mesmo dia da data prevista
    fabrica.devolver(emp["id"])
    assert fabrica.multas(u["id"]) == []
    assert fabrica.get(f"/exemplares/{ex['id']}")["estado"] == "disponivel"


# ------------------------------------------------------------- regra 2
def test_suspensao_por_atraso_superior_a_15_dias(fabrica, relogio):
    u = fabrica.usuario("aluno")
    ex = fabrica.exemplar(fabrica.livro()["id"])
    emp = fabrica.emprestar(u["id"], ex["id"])
    relogio.avancar(dias=7 + 15)
    assert fabrica.get(f"/usuarios/{u['id']}")["situacao"] == "ativo"  # 15 dias: ainda nao
    relogio.avancar(dias=1)
    assert fabrica.get(f"/usuarios/{u['id']}")["situacao"] == "suspenso"  # 16 dias
    relogio.avancar(dias=4)  # 20 dias de atraso
    fabrica.devolver(emp["id"])
    usuario = fabrica.get(f"/usuarios/{u['id']}")
    devolucao = relogio.atual.date()
    assert usuario["suspenso_ate"] == str(devolucao + timedelta(days=40))
    # Ainda suspenso um dia antes do fim
    relogio.avancar(dias=39)
    assert fabrica.get(f"/usuarios/{u['id']}")["situacao"] == "suspenso"
    relogio.avancar(dias=1)
    usuario = fabrica.get(f"/usuarios/{u['id']}")
    assert usuario["situacao"] == "ativo" and usuario["suspenso_ate"] is None


def test_atraso_de_15_dias_nao_suspende(fabrica, relogio):
    u = fabrica.usuario("aluno")
    ex = fabrica.exemplar(fabrica.livro()["id"])
    emp = fabrica.emprestar(u["id"], ex["id"])
    relogio.avancar(dias=7 + 15)
    fabrica.devolver(emp["id"])
    assert fabrica.get(f"/usuarios/{u['id']}")["situacao"] == "ativo"


# ------------------------------------------------------------- regra 3
def test_renovacao_negada_com_fila_de_reserva(client, fabrica):
    u1, u2 = fabrica.usuario(), fabrica.usuario()
    livro = fabrica.livro()
    ex = fabrica.exemplar(livro["id"])
    emp = fabrica.emprestar(u1["id"], ex["id"])
    fabrica.reservar(u2["id"], livro["id"])
    r = client.post(f"/emprestimos/{emp['id']}/renovacao")
    assert r.status_code == 409 and "fila" in r.json()["detail"]


def test_renovacao_negada_se_atrasado(client, fabrica, relogio):
    u = fabrica.usuario()
    ex = fabrica.exemplar(fabrica.livro()["id"])
    emp = fabrica.emprestar(u["id"], ex["id"])
    relogio.avancar(dias=8)
    r = client.post(f"/emprestimos/{emp['id']}/renovacao")
    assert r.status_code == 409 and "atrasado" in r.json()["detail"]


def test_renovacao_estende_prazo(client, fabrica, relogio):
    u = fabrica.usuario("aluno")
    ex = fabrica.exemplar(fabrica.livro()["id"])
    emp = fabrica.emprestar(u["id"], ex["id"])
    relogio.avancar(dias=5)
    r = client.post(f"/emprestimos/{emp['id']}/renovacao").json()
    assert _prevista(r) == relogio.atual + timedelta(days=7)


# ------------------------------------------------------------- regra 4
def test_fila_de_reserva_e_prazo_de_48h(client, fabrica, relogio):
    dono, a, b = fabrica.usuario(), fabrica.usuario(), fabrica.usuario()
    livro = fabrica.livro()
    ex = fabrica.exemplar(livro["id"])
    emp = fabrica.emprestar(dono["id"], ex["id"])

    ra = fabrica.reservar(a["id"], livro["id"])
    relogio.avancar(horas=1)
    rb = fabrica.reservar(b["id"], livro["id"])
    assert (ra["posicao"], rb["posicao"]) == (1, 2)

    relogio.avancar(dias=2)
    fabrica.devolver(emp["id"])
    fila = fabrica.get(f"/livros/{livro['id']}/reservas")
    assert [(r["id"], r["estado"], r["posicao"]) for r in fila] == [
        (ra["id"], "disponivel", None), (rb["id"], "aguardando", 1)]
    assert fabrica.get(f"/exemplares/{ex['id']}")["estado"] == "reservado"
    # Outro usuario nao pode levar o exemplar reservado
    fabrica.emprestar(b["id"], ex["id"], esperado=409)

    # 48h depois, a reserva de A expira e B passa a disponivel
    relogio.avancar(horas=47, )
    assert fabrica.get(f"/reservas/{ra['id']}")["estado"] == "disponivel"
    relogio.avancar(horas=1)
    assert fabrica.get(f"/reservas/{ra['id']}")["estado"] == "expirada"
    rb_atual = fabrica.get(f"/reservas/{rb['id']}")
    assert rb_atual["estado"] == "disponivel" and rb_atual["exemplar_id"] == ex["id"]

    fabrica.emprestar(a["id"], ex["id"], esperado=409)
    fabrica.emprestar(b["id"], ex["id"])
    assert fabrica.get(f"/reservas/{rb['id']}")["estado"] == "atendida"
    assert fabrica.get(f"/livros/{livro['id']}/reservas") == []


def test_expiracoes_encadeadas_respeitam_horario(fabrica, relogio):
    dono, a, b = fabrica.usuario(), fabrica.usuario(), fabrica.usuario()
    livro = fabrica.livro()
    ex = fabrica.exemplar(livro["id"])
    emp = fabrica.emprestar(dono["id"], ex["id"])
    ra = fabrica.reservar(a["id"], livro["id"])
    rb = fabrica.reservar(b["id"], livro["id"])
    fabrica.devolver(emp["id"])
    relogio.avancar(dias=5)  # ambas as janelas de 48h esgotadas
    assert fabrica.get(f"/reservas/{ra['id']}")["estado"] == "expirada"
    assert fabrica.get(f"/reservas/{rb['id']}")["estado"] == "expirada"
    assert fabrica.get(f"/exemplares/{ex['id']}")["estado"] == "disponivel"


def test_cancelar_reserva_disponivel_passa_a_vez(client, fabrica):
    dono, a, b = fabrica.usuario(), fabrica.usuario(), fabrica.usuario()
    livro = fabrica.livro()
    ex = fabrica.exemplar(livro["id"])
    emp = fabrica.emprestar(dono["id"], ex["id"])
    ra = fabrica.reservar(a["id"], livro["id"])
    rb = fabrica.reservar(b["id"], livro["id"])
    fabrica.devolver(emp["id"])
    r = client.post(f"/reservas/{ra['id']}/cancelamento")
    assert r.status_code == 200 and r.json()["estado"] == "cancelada"
    assert fabrica.get(f"/reservas/{rb['id']}")["estado"] == "disponivel"
    assert client.post(f"/reservas/{ra['id']}/cancelamento").status_code == 409


def test_reserva_negada_com_exemplar_disponivel_ou_duplicada(fabrica):
    a, b = fabrica.usuario(), fabrica.usuario()
    livro = fabrica.livro()
    ex = fabrica.exemplar(livro["id"])
    fabrica.reservar(a["id"], livro["id"], esperado=409)  # ha exemplar disponivel
    fabrica.emprestar(a["id"], ex["id"])
    fabrica.reservar(a["id"], livro["id"], esperado=409)  # ja esta com o livro
    fabrica.reservar(b["id"], livro["id"])
    fabrica.reservar(b["id"], livro["id"], esperado=409)  # duplicada


# ------------------------------------------------------------- regra 6
def test_exemplar_em_reparo_ou_baixado_nao_emprestado_nem_reservado(client, fabrica):
    u = fabrica.usuario()
    livro = fabrica.livro()
    reparo = fabrica.exemplar(livro["id"], estado="em_reparo")
    baixado = fabrica.exemplar(livro["id"], estado="baixado")
    fabrica.emprestar(u["id"], reparo["id"], esperado=409)
    fabrica.emprestar(u["id"], baixado["id"], esperado=409)
    fabrica.reservar(u["id"], livro["id"], esperado=409)


def test_baixa_do_ultimo_exemplar_cancela_reservas(client, fabrica):
    dono, a = fabrica.usuario(), fabrica.usuario()
    livro = fabrica.livro()
    ex1 = fabrica.exemplar(livro["id"])
    ex2 = fabrica.exemplar(livro["id"])
    emp = fabrica.emprestar(dono["id"], ex1["id"])
    assert client.patch(f"/exemplares/{ex2['id']}", json={"estado": "em_reparo"}).status_code == 200
    ra = fabrica.reservar(a["id"], livro["id"])
    # Baixar ex2 (em reparo) nao cancela: ex1 ainda circula
    assert client.patch(f"/exemplares/{ex2['id']}", json={"estado": "baixado"}).status_code == 200
    assert fabrica.get(f"/reservas/{ra['id']}")["estado"] == "aguardando"
    # Exemplar emprestado nao pode ser baixado manualmente
    assert client.patch(f"/exemplares/{ex1['id']}", json={"estado": "baixado"}).status_code == 409
    fabrica.devolver(emp["id"])
    # agora ex1 esta reservado para A; A cancela e o exemplar fica disponivel; entao e baixado
    client.post(f"/reservas/{ra['id']}/cancelamento")
    b = fabrica.usuario()
    fabrica.emprestar(b["id"], ex1["id"])
    rc = fabrica.reservar(a["id"], livro["id"])
    assert rc["estado"] == "aguardando"


def test_retorno_de_reparo_atende_fila(client, fabrica):
    dono, a = fabrica.usuario(), fabrica.usuario()
    livro = fabrica.livro()
    ex1 = fabrica.exemplar(livro["id"])
    ex2 = fabrica.exemplar(livro["id"], estado="em_reparo")
    fabrica.emprestar(dono["id"], ex1["id"])
    ra = fabrica.reservar(a["id"], livro["id"])
    client.patch(f"/exemplares/{ex2['id']}", json={"estado": "disponivel"})
    assert fabrica.get(f"/exemplares/{ex2['id']}")["estado"] == "reservado"
    assert fabrica.get(f"/reservas/{ra['id']}")["estado"] == "disponivel"


# ------------------------------------------------------------- regra 7
@pytest.mark.parametrize("categoria,prazo,teto", [("aluno", 7, "30.00"), ("professor", 30, "50.00"),
                                                  ("visitante", 3, "20.00")])
def test_atraso_superior_a_60_dias_baixa_exemplar_e_multa_teto(fabrica, relogio, categoria, prazo, teto):
    dono, a = fabrica.usuario(categoria), fabrica.usuario()
    livro = fabrica.livro()
    ex = fabrica.exemplar(livro["id"])
    emp = fabrica.emprestar(dono["id"], ex["id"])
    ra = fabrica.reservar(a["id"], livro["id"])
    relogio.avancar(dias=prazo + 61)
    fabrica.devolver(emp["id"])
    assert fabrica.get(f"/exemplares/{ex['id']}")["estado"] == "baixado"
    multa = fabrica.multas(dono["id"])[0]
    assert multa["valor"] == teto and multa["estado"] == "aberta"
    # regra 6: ultimo exemplar baixado => reservas canceladas
    assert fabrica.get(f"/reservas/{ra['id']}")["estado"] == "cancelada"


def test_atraso_de_60_dias_nao_baixa(fabrica, relogio):
    u = fabrica.usuario("aluno")
    ex = fabrica.exemplar(fabrica.livro()["id"])
    emp = fabrica.emprestar(u["id"], ex["id"])
    relogio.avancar(dias=7 + 60)
    fabrica.devolver(emp["id"])
    assert fabrica.get(f"/exemplares/{ex['id']}")["estado"] == "disponivel"
