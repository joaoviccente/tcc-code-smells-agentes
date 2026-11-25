from datetime import datetime, timedelta
from fastapi import status


def test_multas_endpoints_e_fluxos(client):
    hoje = datetime.now()

    # Cria aluno e professor
    aluno = client.post(
        "/usuarios",
        json={"nome": "Lucas", "email": "lucas@test.com", "matricula": "A999", "categoria": "aluno"},
    ).json()

    prof = client.post(
        "/usuarios",
        json={"nome": "Prof Xavier", "email": "xavier@test.com", "matricula": "P999", "categoria": "professor"},
    ).json()

    livro = client.post(
        "/livros",
        json={"titulo": "Física I", "autor": "Halliday", "isbn": "12345", "ano": 2015, "area_conhecimento": "Física"},
    ).json()

    ex1 = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "FIS-01"}).json()
    ex2 = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "FIS-02"}).json()

    # Aluno atrasa 3 dias (prazo 7 dias, devolve com 10 dias) -> multa de 3 * 1.00 = 3.00
    emp_aluno = client.post(
        "/emprestimos",
        json={"usuario_id": aluno["id"], "exemplar_id": ex1["id"], "data_retirada": (hoje - timedelta(days=10)).isoformat()},
    ).json()
    client.post(f"/emprestimos/{emp_aluno['id']}/devolver", json={"data_devolucao": hoje.isoformat()})

    # Professor atrasa 1 dia -> multa perdoada
    emp_prof = client.post(
        "/emprestimos",
        json={"usuario_id": prof["id"], "exemplar_id": ex2["id"], "data_retirada": (hoje - timedelta(days=31)).isoformat()},
    ).json()
    client.post(f"/emprestimos/{emp_prof['id']}/devolver", json={"data_devolucao": hoje.isoformat()})

    # 1. Listar multas do aluno
    resp_multas_aluno = client.get(f"/multas/usuario/{aluno['id']}")
    assert resp_multas_aluno.status_code == status.HTTP_200_OK
    multas_a = resp_multas_aluno.json()
    assert len(multas_a) == 1
    multa_aluno_id = multas_a[0]["id"]
    assert multas_a[0]["valor"] == 3.0
    assert multas_a[0]["estado"] == "aberta"

    # 2. Listar multas do professor
    resp_multas_prof = client.get(f"/multas/usuario/{prof['id']}")
    assert resp_multas_prof.status_code == status.HTTP_200_OK
    multas_p = resp_multas_prof.json()
    assert len(multas_p) == 1
    multa_prof_id = multas_p[0]["id"]
    assert multas_p[0]["estado"] == "perdoada"

    # 3. Tentar pagar multa perdoada -> erro 400
    resp_pagar_perdoada = client.post(f"/multas/{multa_prof_id}/pagar")
    assert resp_pagar_perdoada.status_code == status.HTTP_400_BAD_REQUEST
    assert "perdoada" in resp_pagar_perdoada.json()["detail"]

    # 4. Pagar multa do aluno -> sucesso 200
    resp_pagar = client.post(f"/multas/{multa_aluno_id}/pagar")
    assert resp_pagar.status_code == status.HTTP_200_OK
    assert resp_pagar.json()["estado"] == "paga"

    # 5. Tentar pagar novamente multa já paga -> erro 400
    resp_pagar_repetido = client.post(f"/multas/{multa_aluno_id}/pagar")
    assert resp_pagar_repetido.status_code == status.HTTP_400_BAD_REQUEST
    assert "já se encontra paga" in resp_pagar_repetido.json()["detail"]

    # 6. Multa inexistente -> 404
    resp_404 = client.get("/multas/999999")
    assert resp_404.status_code == status.HTTP_404_NOT_FOUND
