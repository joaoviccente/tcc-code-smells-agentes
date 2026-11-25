from datetime import datetime, timedelta
from fastapi import status


def test_emprestimos_casos_de_borda(client):
    hoje = datetime.now()

    aluno1 = client.post(
        "/usuarios",
        json={"nome": "Aluno 1", "email": "a1@test.com", "matricula": "M01", "categoria": "aluno"},
    ).json()

    aluno2 = client.post(
        "/usuarios",
        json={"nome": "Aluno 2", "email": "a2@test.com", "matricula": "M02", "categoria": "aluno"},
    ).json()

    livro = client.post(
        "/livros",
        json={"titulo": "Redes de Computadores", "autor": "Tanenbaum", "isbn": "RC100", "ano": 2011, "area_conhecimento": "Redes"},
    ).json()

    ex1 = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "RED-01"}).json()
    ex2 = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "RED-02"}).json()

    # 1. Tentar emprestar para usuário inexistente -> 404
    resp_u404 = client.post("/emprestimos", json={"usuario_id": 9999, "exemplar_id": ex1["id"]})
    assert resp_u404.status_code == status.HTTP_404_NOT_FOUND

    # 2. Tentar emprestar exemplar inexistente -> 404
    resp_e404 = client.post("/emprestimos", json={"usuario_id": aluno1["id"], "exemplar_id": 9999})
    assert resp_e404.status_code == status.HTTP_404_NOT_FOUND

    # 3. Empresta ex1 para aluno1
    emp1 = client.post("/emprestimos", json={"usuario_id": aluno1["id"], "exemplar_id": ex1["id"]}).json()

    # 4. Tentar emprestar ex1 novamente (já emprestado) -> 400
    resp_emp_dup = client.post("/emprestimos", json={"usuario_id": aluno2["id"], "exemplar_id": ex1["id"]})
    assert resp_emp_dup.status_code == status.HTTP_400_BAD_REQUEST
    assert "já está emprestado" in resp_emp_dup.json()["detail"]

    # 5. Devolver empréstimo já devolvido -> 400
    client.post(f"/emprestimos/{emp1['id']}/devolver")
    resp_dev_dup = client.post(f"/emprestimos/{emp1['id']}/devolver")
    assert resp_dev_dup.status_code == status.HTTP_400_BAD_REQUEST
    assert "já foi devolvido" in resp_dev_dup.json()["detail"]

    # 6. Renovar empréstimo já devolvido -> 400
    resp_ren_dev = client.post(f"/emprestimos/{emp1['id']}/renovar")
    assert resp_ren_dev.status_code == status.HTTP_400_BAD_REQUEST
    assert "já foi devolvido" in resp_ren_dev.json()["detail"]


def test_emprestimo_exemplar_reservado_outro_usuario(client):
    hoje = datetime.now()

    u1 = client.post(
        "/usuarios",
        json={"nome": "U1", "email": "u1@test.com", "matricula": "U10", "categoria": "aluno"},
    ).json()

    u2 = client.post(
        "/usuarios",
        json={"nome": "U2", "email": "u2@test.com", "matricula": "U20", "categoria": "aluno"},
    ).json()

    livro = client.post(
        "/livros",
        json={"titulo": "Banco de Dados", "autor": "Navathe", "isbn": "BD100", "ano": 2015, "area_conhecimento": "Banco de Dados"},
    ).json()

    ex = client.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": "BD-01"}).json()

    # Empresta ex para u1
    emp = client.post(
        "/emprestimos",
        json={"usuario_id": u1["id"], "exemplar_id": ex["id"], "data_retirada": (hoje - timedelta(days=2)).isoformat()},
    ).json()

    # u2 reserva o livro
    client.post("/reservas", json={"usuario_id": u2["id"], "livro_id": livro["id"]})

    # u1 devolve -> ex fica reservado para u2 (reserva de u2 passa a 'disponivel')
    client.post(f"/emprestimos/{emp['id']}/devolver", json={"data_devolucao": hoje.isoformat()})

    ex_check = client.get(f"/exemplares/{ex['id']}").json()
    assert ex_check["estado"] == "reservado"

    # u1 tenta pegar o exemplar reservado para u2 -> 400
    resp_u1_tenta = client.post("/emprestimos", json={"usuario_id": u1["id"], "exemplar_id": ex["id"]})
    assert resp_u1_tenta.status_code == status.HTTP_400_BAD_REQUEST
    assert "reservado para outro usuário" in resp_u1_tenta.json()["detail"]

    # u2 pega o exemplar reservado para ele -> Sucesso 201!
    resp_u2_pega = client.post("/emprestimos", json={"usuario_id": u2["id"], "exemplar_id": ex["id"]})
    assert resp_u2_pega.status_code == status.HTTP_201_CREATED
