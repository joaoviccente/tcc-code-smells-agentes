from datetime import datetime, timedelta
import uuid
from app.utils import get_utcnow


def _setup_livro_com_usuarios(client):
    l = client.post("/livros", json={
        "titulo": "Inteligência Artificial",
        "autor": "Stuart Russell",
        "isbn": f"ISBN-AI-{uuid.uuid4().hex[:8]}",
        "ano": 2020,
        "area": "Computação"
    }).json()

    ex = client.post("/exemplares", json={
        "livro_id": l["id"],
        "codigo_tombo": f"TOMBO-AI-{uuid.uuid4().hex[:8]}"
    }).json()

    u1 = client.post("/usuarios", json={
        "nome": "User 1",
        "email": f"u1_{uuid.uuid4().hex[:8]}@teste.com",
        "matricula": f"M1-{uuid.uuid4().hex[:8]}",
        "categoria": "aluno"
    }).json()

    u2 = client.post("/usuarios", json={
        "nome": "User 2",
        "email": f"u2_{uuid.uuid4().hex[:8]}@teste.com",
        "matricula": f"M2-{uuid.uuid4().hex[:8]}",
        "categoria": "aluno"
    }).json()

    u3 = client.post("/usuarios", json={
        "nome": "User 3",
        "email": f"u3_{uuid.uuid4().hex[:8]}@teste.com",
        "matricula": f"M3-{uuid.uuid4().hex[:8]}",
        "categoria": "aluno"
    }).json()

    return l, ex, u1, u2, u3


def test_fila_reservas_ordem_de_chegada(client):
    l, ex, u1, u2, u3 = _setup_livro_com_usuarios(client)

    # u1 faz empréstimo
    client.post("/emprestimos", json={"usuario_id": u1["id"], "exemplar_id": ex["id"]})

    # u2 reserva primeiro -> posição 1
    r2 = client.post("/reservas", json={"livro_id": l["id"], "usuario_id": u2["id"]}).json()
    assert r2["posicao_fila"] == 1
    assert r2["estado"] == "aguardando"

    # u3 reserva em seguida -> posição 2
    r3 = client.post("/reservas", json={"livro_id": l["id"], "usuario_id": u3["id"]}).json()
    assert r3["posicao_fila"] == 2
    assert r3["estado"] == "aguardando"

    # Listar fila do livro
    fila = client.get(f"/reservas/livro/{l['id']}").json()
    assert len(fila) == 2
    assert fila[0]["id"] == r2["id"]
    assert fila[1]["id"] == r3["id"]


def test_devolucao_ativa_primeiro_da_fila_com_48_horas(client):
    l, ex, u1, u2, u3 = _setup_livro_com_usuarios(client)

    emp = client.post("/emprestimos", json={"usuario_id": u1["id"], "exemplar_id": ex["id"]}).json()
    r2 = client.post("/reservas", json={"livro_id": l["id"], "usuario_id": u2["id"]}).json()
    r3 = client.post("/reservas", json={"livro_id": l["id"], "usuario_id": u3["id"]}).json()

    # u1 devolve o exemplar
    now = get_utcnow()
    client.post(f"/emprestimos/{emp['id']}/devolver", json={"data_devolucao": now.isoformat()})

    # Exemplar passa para 'reservado'
    ex_atual = client.get(f"/exemplares/{ex['id']}").json()
    assert ex_atual["estado"] == "reservado"

    # r2 passa para 'disponivel' com prazo de 48h
    r2_atual = client.get(f"/reservas/{r2['id']}").json()
    assert r2_atual["estado"] == "disponivel"
    assert r2_atual["data_limite_retirada"] is not None
    limite = datetime.fromisoformat(r2_atual["data_limite_retirada"])
    diff_horas = (limite - now).total_seconds() / 3600
    assert abs(diff_horas - 48.0) < 0.1

    # r3 continua 'aguardando'
    r3_atual = client.get(f"/reservas/{r3['id']}").json()
    assert r3_atual["estado"] == "aguardando"


def test_expiracao_48h_passa_a_vez_ao_proximo(client):
    l, ex, u1, u2, u3 = _setup_livro_com_usuarios(client)

    emp = client.post("/emprestimos", json={"usuario_id": u1["id"], "exemplar_id": ex["id"]}).json()
    r2 = client.post("/reservas", json={"livro_id": l["id"], "usuario_id": u2["id"]}).json()
    r3 = client.post("/reservas", json={"livro_id": l["id"], "usuario_id": u3["id"]}).json()

    # Devolve no momento T
    t0 = get_utcnow() - timedelta(hours=50)  # Devolvido há 50 horas
    client.post(f"/emprestimos/{emp['id']}/devolver", json={"data_devolucao": t0.isoformat()})

    # Ao processar ou consultar, r2 já excedeu 48 horas (50h > 48h)
    client.post("/reservas/processar-expiradas")

    # r2 deve estar 'expirada'
    r2_atual = client.get(f"/reservas/{r2['id']}").json()
    assert r2_atual["estado"] == "expirada"

    # r3 deve agora ter passado para 'disponivel'
    r3_atual = client.get(f"/reservas/{r3['id']}").json()
    assert r3_atual["estado"] == "disponivel"
    assert r3_atual["posicao_fila"] == 1


def test_cancelamento_reserva(client):
    l, ex, u1, u2, u3 = _setup_livro_com_usuarios(client)

    r2 = client.post("/reservas", json={"livro_id": l["id"], "usuario_id": u2["id"]}).json()
    r3 = client.post("/reservas", json={"livro_id": l["id"], "usuario_id": u3["id"]}).json()

    # u2 cancela sua reserva
    cancel_res = client.post(f"/reservas/{r2['id']}/cancelar")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["estado"] == "cancelada"

    # Fila reorganizada: u3 agora é o 1º
    fila = client.get(f"/reservas/livro/{l['id']}").json()
    assert len(fila) == 1
    assert fila[0]["id"] == r3["id"]
    assert fila[0]["posicao_fila"] == 1


def test_cancelamento_todas_reservas_se_ultimo_exemplar_baixado(client):
    # Regra 6: se o último exemplar disponível de um livro for baixado,
    # todas as reservas daquele livro são canceladas.
    l, ex, u1, u2, u3 = _setup_livro_com_usuarios(client)

    r2 = client.post("/reservas", json={"livro_id": l["id"], "usuario_id": u2["id"]}).json()
    r3 = client.post("/reservas", json={"livro_id": l["id"], "usuario_id": u3["id"]}).json()

    # Baixar o exemplar (único exemplar deste livro)
    client.put(f"/exemplares/{ex['id']}", json={"estado": "baixado"})

    # Ambas as reservas devem ser automaticamente canceladas
    r2_check = client.get(f"/reservas/{r2['id']}").json()
    r3_check = client.get(f"/reservas/{r3['id']}").json()
    assert r2_check["estado"] == "cancelada"
    assert r3_check["estado"] == "cancelada"

    # Fila do livro agora está vazia
    fila = client.get(f"/reservas/livro/{l['id']}").json()
    assert len(fila) == 0


def test_reserva_bloqueada_se_exemplar_em_reparo_ou_baixado(client):
    # Regra 6: Exemplar em reparo ou baixado não pode ser reservado
    l = client.post("/livros", json={
        "titulo": "Compiladores",
        "autor": "Aho",
        "isbn": f"ISBN-COMP-{uuid.uuid4().hex[:8]}",
        "ano": 2006,
        "area": "Computação"
    }).json()

    client.post("/exemplares", json={
        "livro_id": l["id"],
        "codigo_tombo": "T-REPARO",
        "estado": "em_reparo"
    })

    u = client.post("/usuarios", json={
        "nome": "Aluno Teste",
        "email": f"aluno_{uuid.uuid4().hex[:8]}@teste.com",
        "matricula": f"MAT-AL-{uuid.uuid4().hex[:8]}",
        "categoria": "aluno"
    }).json()

    res = client.post("/reservas", json={"livro_id": l["id"], "usuario_id": u["id"]})
    assert res.status_code == 400
    assert "reparo ou baixados" in res.json()["detail"]
