from datetime import datetime, timedelta
from decimal import Decimal
from app.utils import get_utcnow


def test_fluxo_pagamento_multa(client):
    # Criar aluno
    u = client.post("/usuarios", json={
        "nome": "Maria Aluna",
        "email": "maria@teste.com",
        "matricula": "MAT-MARIA-1",
        "categoria": "aluno"
    }).json()

    l = client.post("/livros", json={
        "titulo": "Cálculo 1",
        "autor": "James Stewart",
        "isbn": "9788522112586",
        "ano": 2013,
        "area": "Matemática"
    }).json()

    ex1 = client.post("/exemplares", json={"livro_id": l["id"], "codigo_tombo": "TOMBO-CALC-1"}).json()
    ex2 = client.post("/exemplares", json={"livro_id": l["id"], "codigo_tombo": "TOMBO-CALC-2"}).json()

    now = get_utcnow()
    # Empréstimo com devolução atrasada em 4 dias (Aluno: 7 dias prazo, retirada há 11 dias)
    emp = client.post("/emprestimos", json={
        "usuario_id": u["id"],
        "exemplar_id": ex1["id"],
        "data_retirada": (now - timedelta(days=11)).isoformat()
    }).json()

    client.post(f"/emprestimos/{emp['id']}/devolver", json={"data_devolucao": now.isoformat()})

    # Listar multas do usuário
    multas = client.get(f"/multas/usuario/{u['id']}").json()
    assert len(multas) == 1
    multa = multas[0]
    assert multa["estado"] == "aberta"
    assert Decimal(str(multa["valor"])) == Decimal("4.00")

    # Novo empréstimo bloqueado por multa aberta
    bloqueio = client.post("/emprestimos", json={"usuario_id": u["id"], "exemplar_id": ex2["id"]})
    assert bloqueio.status_code == 400

    # Pagar a multa
    pagamento = client.post(f"/multas/{multa['id']}/pagar")
    assert pagamento.status_code == 200
    assert pagamento.json()["estado"] == "paga"
    assert pagamento.json()["data_pagamento"] is not None

    # Agora o novo empréstimo deve ser permitido!
    sucesso = client.post("/emprestimos", json={"usuario_id": u["id"], "exemplar_id": ex2["id"]})
    assert sucesso.status_code == 201
