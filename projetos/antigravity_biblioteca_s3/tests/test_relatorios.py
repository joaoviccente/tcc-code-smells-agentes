from datetime import datetime, timedelta
from app.utils import get_utcnow


def test_relatorios(client):
    # Criar usuários
    u1 = client.post("/usuarios", json={
        "nome": "Alice", "email": "alice@rel.com", "matricula": "M-REL-1", "categoria": "aluno"
    }).json()
    u2 = client.post("/usuarios", json={
        "nome": "Bob", "email": "bob@rel.com", "matricula": "M-REL-2", "categoria": "professor"
    }).json()

    # Criar livros de diferentes áreas
    l1 = client.post("/livros", json={
        "titulo": "Física 1", "autor": "Halliday", "isbn": "ISBN-F1", "ano": 2014, "area": "Física"
    }).json()
    l2 = client.post("/livros", json={
        "titulo": "Química Geral", "autor": "Atkins", "isbn": "ISBN-Q1", "ano": 2015, "area": "Química"
    }).json()

    # Exemplares de Física
    ex_f1 = client.post("/exemplares", json={"livro_id": l1["id"], "codigo_tombo": "T-F1"}).json()
    ex_f2 = client.post("/exemplares", json={"livro_id": l1["id"], "codigo_tombo": "T-F2"}).json()

    # Exemplares de Química
    ex_q1 = client.post("/exemplares", json={"livro_id": l2["id"], "codigo_tombo": "T-Q1"}).json()

    now = get_utcnow()

    # Empréstimos: Livro 1 (Física) emprestado 2 vezes
    e1 = client.post("/emprestimos", json={
        "usuario_id": u1["id"], "exemplar_id": ex_f1["id"], "data_retirada": (now - timedelta(days=20)).isoformat()
    }).json()
    # u1 devolve com atraso de 13 dias (Aluno prazo 7 dias -> 20 - 7 = 13 dias de atraso)
    client.post(f"/emprestimos/{e1['id']}/devolver", json={"data_devolucao": now.isoformat()})

    # Segundo empréstimo do Livro 1
    client.post("/emprestimos", json={
        "usuario_id": u2["id"], "exemplar_id": ex_f1["id"], "data_retirada": now.isoformat()
    })

    # Empréstimo do Livro 2 (Química)
    client.post("/emprestimos", json={
        "usuario_id": u2["id"], "exemplar_id": ex_q1["id"], "data_retirada": now.isoformat()
    })

    # 1. Relatório: Livros mais emprestados
    rel_livros = client.get("/relatorios/livros-mais-emprestados").json()
    assert len(rel_livros) >= 2
    # Livro 1 deve ser o primeiro com 2 empréstimos
    assert rel_livros[0]["livro_id"] == l1["id"]
    assert rel_livros[0]["total_emprestimos"] == 2
    # Livro 2 com 1 empréstimo
    assert rel_livros[1]["livro_id"] == l2["id"]
    assert rel_livros[1]["total_emprestimos"] == 1

    # 2. Relatório: Usuários com mais atrasos
    rel_usuarios = client.get("/relatorios/usuarios-mais-atrasos").json()
    assert len(rel_usuarios) >= 1
    assert rel_usuarios[0]["usuario_id"] == u1["id"]
    assert rel_usuarios[0]["total_atrasos"] == 1
    assert rel_usuarios[0]["total_dias_atraso"] == 13

    # 3. Relatório: Taxa de ocupação do acervo por área
    rel_ocupacao = client.get("/relatorios/taxa-ocupacao-acervo").json()
    # Áreas: Física (2 exemplares, 1 emprestado -> 50%), Química (1 exemplar, 1 emprestado -> 100%)
    ocupacao_dict = {r["area"]: r for r in rel_ocupacao}
    assert "Física" in ocupacao_dict
    assert "Química" in ocupacao_dict
    assert ocupacao_dict["Química"]["taxa_ocupacao_percentual"] == 100.0
    assert ocupacao_dict["Física"]["taxa_ocupacao_percentual"] == 50.0
