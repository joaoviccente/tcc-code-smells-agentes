from datetime import datetime, timedelta
from decimal import Decimal
import uuid
from app.utils import get_utcnow


def _criar_cenario_base(client, categoria="aluno", situacao="ativo"):
    u = client.post("/usuarios", json={
        "nome": f"Usuario {categoria}",
        "email": f"user_{categoria}_{uuid.uuid4().hex[:8]}@teste.com",
        "matricula": f"MAT-{categoria}-{uuid.uuid4().hex[:8]}",
        "categoria": categoria,
        "situacao": situacao
    }).json()

    l = client.post("/livros", json={
        "titulo": "Livro de Teste",
        "autor": "Autor Teste",
        "isbn": f"ISBN-{uuid.uuid4().hex[:8]}",
        "ano": 2024,
        "area": "Geral"
    }).json()

    ex = client.post("/exemplares", json={
        "livro_id": l["id"],
        "codigo_tombo": f"TOMBO-{uuid.uuid4().hex[:8]}",
        "estado": "disponivel"
    }).json()

    return u, l, ex


def test_prazos_por_categoria(client):
    # Aluno: 7 dias
    u_aluno, _, ex_aluno = _criar_cenario_base(client, "aluno")
    emp_aluno = client.post("/emprestimos", json={
        "usuario_id": u_aluno["id"],
        "exemplar_id": ex_aluno["id"]
    }).json()
    retirada = datetime.fromisoformat(emp_aluno["data_retirada"])
    prevista = datetime.fromisoformat(emp_aluno["data_prevista"])
    assert (prevista.date() - retirada.date()).days == 7

    # Professor: 30 dias
    u_prof, _, ex_prof = _criar_cenario_base(client, "professor")
    emp_prof = client.post("/emprestimos", json={
        "usuario_id": u_prof["id"],
        "exemplar_id": ex_prof["id"]
    }).json()
    retirada_p = datetime.fromisoformat(emp_prof["data_retirada"])
    prevista_p = datetime.fromisoformat(emp_prof["data_prevista"])
    assert (prevista_p.date() - retirada_p.date()).days == 30

    # Visitante: 3 dias
    u_vis, _, ex_vis = _criar_cenario_base(client, "visitante")
    emp_vis = client.post("/emprestimos", json={
        "usuario_id": u_vis["id"],
        "exemplar_id": ex_vis["id"]
    }).json()
    retirada_v = datetime.fromisoformat(emp_vis["data_retirada"])
    prevista_v = datetime.fromisoformat(emp_vis["data_prevista"])
    assert (prevista_v.date() - retirada_v.date()).days == 3


def test_limite_exemplares_por_categoria(client):
    # Aluno: limite 3
    u_aluno, l, _ = _criar_cenario_base(client, "aluno")
    for i in range(3):
        ex = client.post("/exemplares", json={
            "livro_id": l["id"],
            "codigo_tombo": f"T-ALUNO-{i}"
        }).json()
        res = client.post("/emprestimos", json={"usuario_id": u_aluno["id"], "exemplar_id": ex["id"]})
        assert res.status_code == 201

    # 4º empréstimo deve falhar
    ex_extra = client.post("/exemplares", json={
        "livro_id": l["id"],
        "codigo_tombo": "T-ALUNO-EXTRA"
    }).json()
    res_bloqueio = client.post("/emprestimos", json={"usuario_id": u_aluno["id"], "exemplar_id": ex_extra["id"]})
    assert res_bloqueio.status_code == 400
    assert "Limite de empréstimos atingido" in res_bloqueio.json()["detail"]


def test_limite_exemplares_visitante(client):
    # Visitante: limite 1
    u_vis, l, _ = _criar_cenario_base(client, "visitante")
    ex1 = client.post("/exemplares", json={"livro_id": l["id"], "codigo_tombo": "T-VIS-1"}).json()
    ex2 = client.post("/exemplares", json={"livro_id": l["id"], "codigo_tombo": "T-VIS-2"}).json()

    res1 = client.post("/emprestimos", json={"usuario_id": u_vis["id"], "exemplar_id": ex1["id"]})
    assert res1.status_code == 201

    res2 = client.post("/emprestimos", json={"usuario_id": u_vis["id"], "exemplar_id": ex2["id"]})
    assert res2.status_code == 400


def test_bloqueio_usuario_suspenso_ou_com_multa(client):
    # Usuário suspenso
    u_susp, _, ex1 = _criar_cenario_base(client, "aluno", situacao="suspenso")
    res_susp = client.post("/emprestimos", json={"usuario_id": u_susp["id"], "exemplar_id": ex1["id"]})
    assert res_susp.status_code == 400
    assert "suspenso" in res_susp.json()["detail"]

    # Usuário com multa em aberto
    u_aluno, _, ex2 = _criar_cenario_base(client, "aluno")
    # Fazer empréstimo e devolver com atraso para gerar multa aberta
    now = get_utcnow()
    emp = client.post("/emprestimos", json={
        "usuario_id": u_aluno["id"],
        "exemplar_id": ex2["id"],
        "data_retirada": (now - timedelta(days=12)).isoformat()
    }).json()
    # Devolver com atraso de 5 dias (aluno prazo = 7 dias, devolução no dia 12 -> 5 dias atraso)
    client.post(f"/emprestimos/{emp['id']}/devolver", json={
        "data_devolucao": now.isoformat()
    })

    # Tentar novo empréstimo com exemplar novo
    _, _, ex3 = _criar_cenario_base(client, "aluno")
    res_multa = client.post("/emprestimos", json={"usuario_id": u_aluno["id"], "exemplar_id": ex3["id"]})
    assert res_multa.status_code == 400
    assert "multa(s) em aberto" in res_multa.json()["detail"]


def test_renovacoes_por_categoria(client):
    # Aluno: 2 renovações permitidas
    u_aluno, _, ex_aluno = _criar_cenario_base(client, "aluno")
    emp = client.post("/emprestimos", json={
        "usuario_id": u_aluno["id"],
        "exemplar_id": ex_aluno["id"]
    }).json()

    # 1ª renovação
    res1 = client.post(f"/emprestimos/{emp['id']}/renovar")
    assert res1.status_code == 200
    assert res1.json()["numero_renovacoes"] == 1

    # 2ª renovação
    res2 = client.post(f"/emprestimos/{emp['id']}/renovar")
    assert res2.status_code == 200
    assert res2.json()["numero_renovacoes"] == 2

    # 3ª renovação (deve falhar)
    res3 = client.post(f"/emprestimos/{emp['id']}/renovar")
    assert res3.status_code == 400
    assert "limite de renovações atingido" in res3.json()["detail"]


def test_renovacao_visitante_proibida(client):
    # Visitante: 0 renovações
    u_vis, _, ex = _criar_cenario_base(client, "visitante")
    emp = client.post("/emprestimos", json={
        "usuario_id": u_vis["id"],
        "exemplar_id": ex["id"]
    }).json()

    res = client.post(f"/emprestimos/{emp['id']}/renovar")
    assert res.status_code == 400
    assert "limite de renovações atingido" in res.json()["detail"]


def test_renovacao_bloqueada_por_reserva(client):
    u1, l, ex = _criar_cenario_base(client, "aluno")
    u2, _, _ = _criar_cenario_base(client, "aluno")

    emp = client.post("/emprestimos", json={
        "usuario_id": u1["id"],
        "exemplar_id": ex["id"]
    }).json()

    # u2 reserva o livro
    client.post("/reservas", json={"livro_id": l["id"], "usuario_id": u2["id"]})

    # u1 tenta renovar
    res = client.post(f"/emprestimos/{emp['id']}/renovar")
    assert res.status_code == 400
    assert "há reservas na fila" in res.json()["detail"]


def test_multa_professor_tolerancia_2_dias(client):
    # Professor com 2 dias de atraso -> perdoada automaticamente
    u_prof, _, ex = _criar_cenario_base(client, "professor")
    now = get_utcnow()
    # Professor tem 30 dias de prazo. Retirada há 32 dias = 2 dias de atraso
    emp = client.post("/emprestimos", json={
        "usuario_id": u_prof["id"],
        "exemplar_id": ex["id"],
        "data_retirada": (now - timedelta(days=32)).isoformat()
    }).json()

    dev = client.post(f"/emprestimos/{emp['id']}/devolver", json={
        "data_devolucao": now.isoformat()
    }).json()

    assert dev["multa"] is not None
    assert dev["multa"]["estado"] == "perdoada"
    assert Decimal(str(dev["multa"]["valor"])) == Decimal("1.00")  # 2 * 0.50


def test_multa_professor_atraso_3_dias(client):
    # Professor com 3 dias de atraso -> cobrada normalmente (R$ 1,50 aberta)
    u_prof, _, ex = _criar_cenario_base(client, "professor")
    now = get_utcnow()
    # Retirada há 33 dias = 3 dias de atraso
    emp = client.post("/emprestimos", json={
        "usuario_id": u_prof["id"],
        "exemplar_id": ex["id"],
        "data_retirada": (now - timedelta(days=33)).isoformat()
    }).json()

    dev = client.post(f"/emprestimos/{emp['id']}/devolver", json={
        "data_devolucao": now.isoformat()
    }).json()

    assert dev["multa"] is not None
    assert dev["multa"]["estado"] == "aberta"
    assert Decimal(str(dev["multa"]["valor"])) == Decimal("1.50")  # 3 * 0.50


def test_teto_multa_aluno(client):
    # Aluno: R$ 1,00/dia; teto R$ 30,00.
    # Atraso de 40 dias -> multa R$ 30,00.
    u_aluno, _, ex = _criar_cenario_base(client, "aluno")
    now = get_utcnow()
    # Prazo 7 dias. Retirada há 47 dias = 40 dias de atraso
    emp = client.post("/emprestimos", json={
        "usuario_id": u_aluno["id"],
        "exemplar_id": ex["id"],
        "data_retirada": (now - timedelta(days=47)).isoformat()
    }).json()

    dev = client.post(f"/emprestimos/{emp['id']}/devolver", json={
        "data_devolucao": now.isoformat()
    }).json()

    assert dev["multa"] is not None
    assert dev["multa"]["estado"] == "aberta"
    assert Decimal(str(dev["multa"]["valor"])) == Decimal("30.00")


def test_suspensao_automatica_atraso_maior_que_15_dias(client):
    # Regra 2: atraso superior a 15 dias suspende o usuário pelo dobro dos dias de atraso
    u_aluno, _, ex = _criar_cenario_base(client, "aluno")
    now = get_utcnow()
    # Prazo 7 dias. Retirada há 25 dias = 18 dias de atraso
    emp = client.post("/emprestimos", json={
        "usuario_id": u_aluno["id"],
        "exemplar_id": ex["id"],
        "data_retirada": (now - timedelta(days=25)).isoformat()
    }).json()

    dev = client.post(f"/emprestimos/{emp['id']}/devolver", json={
        "data_devolucao": now.isoformat()
    }).json()

    # Verificar situação do usuário
    u_atual = client.get(f"/usuarios/{u_aluno['id']}").json()
    assert u_atual["situacao"] == "suspenso"
    assert u_atual["data_suspensao_fim"] is not None
    fim = datetime.fromisoformat(u_atual["data_suspensao_fim"])
    # 18 dias de atraso * 2 = 36 dias de suspensão
    dias_suspensao = (fim.date() - now.date()).days
    assert dias_suspensao == 36


def test_baixa_exemplar_atraso_maior_que_60_dias(client):
    # Regra 7: devolução com mais de 60 dias de atraso marca exemplar como baixado e gera multa no teto
    u_aluno, _, ex = _criar_cenario_base(client, "aluno")
    now = get_utcnow()
    # Prazo 7 dias. Retirada há 70 dias = 63 dias de atraso
    emp = client.post("/emprestimos", json={
        "usuario_id": u_aluno["id"],
        "exemplar_id": ex["id"],
        "data_retirada": (now - timedelta(days=70)).isoformat()
    }).json()

    dev = client.post(f"/emprestimos/{emp['id']}/devolver", json={
        "data_devolucao": now.isoformat()
    }).json()

    # Exemplar deve estar baixado
    ex_atual = client.get(f"/exemplares/{ex['id']}").json()
    assert ex_atual["estado"] == "baixado"

    # Multa deve ser no valor do teto (Aluno = 30.00)
    assert dev["multa"] is not None
    assert Decimal(str(dev["multa"]["valor"])) == Decimal("30.00")
    assert dev["multa"]["estado"] == "aberta"
