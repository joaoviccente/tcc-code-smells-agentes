from datetime import datetime, timedelta
from decimal import Decimal
import uuid
from app.utils import get_utcnow


def test_retirada_de_exemplar_reservado_por_usuario_correto(client):
    # Setup: 1 livro, 1 exemplar, 2 alunos (u1 e u2)
    l = client.post("/livros", json={
        "titulo": "Arquitetura de Computadores",
        "autor": "Patterson e Hennessy",
        "isbn": f"ISBN-{uuid.uuid4().hex[:8]}",
        "ano": 2017,
        "area": "Hardware"
    }).json()

    ex = client.post("/exemplares", json={"livro_id": l["id"], "codigo_tombo": f"T-{uuid.uuid4().hex[:8]}"}).json()

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

    # u1 pega emprestado
    emp1 = client.post("/emprestimos", json={"usuario_id": u1["id"], "exemplar_id": ex["id"]}).json()

    # u2 reserva o livro
    res2 = client.post("/reservas", json={"livro_id": l["id"], "usuario_id": u2["id"]}).json()

    # u1 devolve -> exemplar fica 'reservado' e res2 fica 'disponivel'
    now = get_utcnow()
    client.post(f"/emprestimos/{emp1['id']}/devolver", json={"data_devolucao": now.isoformat()})

    ex_check = client.get(f"/exemplares/{ex['id']}").json()
    assert ex_check["estado"] == "reservado"

    # u3 tenta pegar o exemplar reservado para u2 -> DEVE FALHAR (400)
    emp_invasor = client.post("/emprestimos", json={"usuario_id": u3["id"], "exemplar_id": ex["id"]})
    assert emp_invasor.status_code == 400
    assert "reservado para outro usuário" in emp_invasor.json()["detail"]

    # u2 (o dono da reserva) retira o exemplar -> DEVE TER SUCESSO (201)
    emp_dono = client.post("/emprestimos", json={"usuario_id": u2["id"], "exemplar_id": ex["id"]})
    assert emp_dono.status_code == 201

    # Exemplar agora deve estar 'emprestado'
    ex_pos = client.get(f"/exemplares/{ex['id']}").json()
    assert ex_pos["estado"] == "emprestado"


def test_exemplar_em_reparo_nao_pode_ser_emprestado(client):
    l = client.post("/livros", json={
        "titulo": "Compiladores",
        "autor": "Aho",
        "isbn": f"ISBN-{uuid.uuid4().hex[:8]}",
        "ano": 2006,
        "area": "Computação"
    }).json()

    ex = client.post("/exemplares", json={
        "livro_id": l["id"],
        "codigo_tombo": f"T-{uuid.uuid4().hex[:8]}",
        "estado": "em_reparo"
    }).json()

    u = client.post("/usuarios", json={
        "nome": "Aluno",
        "email": f"aluno_{uuid.uuid4().hex[:8]}@teste.com",
        "matricula": f"M-{uuid.uuid4().hex[:8]}",
        "categoria": "aluno"
    }).json()

    res = client.post("/emprestimos", json={"usuario_id": u["id"], "exemplar_id": ex["id"]})
    assert res.status_code == 400
    assert "em_reparo" in res.json()["detail"]


def test_regra_professor_4_renovacoes(client):
    # Professor tem direito a 4 renovações (30 dias cada)
    u = client.post("/usuarios", json={
        "nome": "Professor Pardal",
        "email": f"prof_{uuid.uuid4().hex[:8]}@teste.com",
        "matricula": f"M-PROF-{uuid.uuid4().hex[:8]}",
        "categoria": "professor"
    }).json()

    l = client.post("/livros", json={
        "titulo": "Física Quântica",
        "autor": "Eisberg",
        "isbn": f"ISBN-{uuid.uuid4().hex[:8]}",
        "ano": 1979,
        "area": "Física"
    }).json()

    ex = client.post("/exemplares", json={"livro_id": l["id"], "codigo_tombo": f"T-{uuid.uuid4().hex[:8]}"}).json()

    emp = client.post("/emprestimos", json={"usuario_id": u["id"], "exemplar_id": ex["id"]}).json()

    # Executar 4 renovações válidas
    for i in range(1, 5):
        res = client.post(f"/emprestimos/{emp['id']}/renovar")
        assert res.status_code == 200
        assert res.json()["numero_renovacoes"] == i

    # 5ª renovação deve ser negada
    res5 = client.post(f"/emprestimos/{emp['id']}/renovar")
    assert res5.status_code == 400
    assert "limite de renovações atingido" in res5.json()["detail"]


def test_visitante_multa_e_teto(client):
    # Visitante: multa R$ 2,00 por dia, teto R$ 20,00
    u = client.post("/usuarios", json={
        "nome": "Visitante 1",
        "email": f"vis_{uuid.uuid4().hex[:8]}@teste.com",
        "matricula": f"M-VIS-{uuid.uuid4().hex[:8]}",
        "categoria": "visitante"
    }).json()

    l = client.post("/livros", json={
        "titulo": "Guia da Cidade",
        "autor": "Prefeitura",
        "isbn": f"ISBN-{uuid.uuid4().hex[:8]}",
        "ano": 2022,
        "area": "Turismo"
    }).json()

    ex = client.post("/exemplares", json={"livro_id": l["id"], "codigo_tombo": f"T-{uuid.uuid4().hex[:8]}"}).json()

    now = get_utcnow()
    # Prazo visitante: 3 dias. Retirada há 15 dias -> atraso de 12 dias.
    # 12 * 2.00 = 24.00 -> limitado ao teto de 20.00!
    emp = client.post("/emprestimos", json={
        "usuario_id": u["id"],
        "exemplar_id": ex["id"],
        "data_retirada": (now - timedelta(days=15)).isoformat()
    }).json()

    dev = client.post(f"/emprestimos/{emp['id']}/devolver", json={"data_devolucao": now.isoformat()}).json()
    assert dev["multa"] is not None
    assert Decimal(str(dev["multa"]["valor"])) == Decimal("20.00")
    assert dev["multa"]["estado"] == "aberta"


def test_bloqueio_exclusao_entidades_com_emprestimos_ativos(client):
    # Usuário com empréstimo ativo não pode ser excluído
    u = client.post("/usuarios", json={
        "nome": "User Excluir",
        "email": f"uex_{uuid.uuid4().hex[:8]}@teste.com",
        "matricula": f"MEX-{uuid.uuid4().hex[:8]}",
        "categoria": "aluno"
    }).json()

    l = client.post("/livros", json={
        "titulo": "Livro Excluir",
        "autor": "Autor",
        "isbn": f"ISBN-{uuid.uuid4().hex[:8]}",
        "ano": 2021,
        "area": "Geral"
    }).json()

    ex = client.post("/exemplares", json={"livro_id": l["id"], "codigo_tombo": f"T-{uuid.uuid4().hex[:8]}"}).json()

    client.post("/emprestimos", json={"usuario_id": u["id"], "exemplar_id": ex["id"]})

    # Tentar excluir usuário -> 400
    res_u = client.delete(f"/usuarios/{u['id']}")
    assert res_u.status_code == 400

    # Tentar excluir exemplar -> 400
    res_ex = client.delete(f"/exemplares/{ex['id']}")
    assert res_ex.status_code == 400

    # Tentar excluir livro -> 400
    res_l = client.delete(f"/livros/{l['id']}")
    assert res_l.status_code == 400


def test_filtro_periodo_relatorio_livros(client):
    # Cria empréstimo em data específica
    u = client.post("/usuarios", json={
        "nome": "Rel User",
        "email": f"rel_{uuid.uuid4().hex[:8]}@teste.com",
        "matricula": f"M-R-{uuid.uuid4().hex[:8]}",
        "categoria": "aluno"
    }).json()

    l = client.post("/livros", json={
        "titulo": "Livro Periodo",
        "autor": "Autor",
        "isbn": f"ISBN-{uuid.uuid4().hex[:8]}",
        "ano": 2021,
        "area": "Geral"
    }).json()

    ex = client.post("/exemplares", json={"livro_id": l["id"], "codigo_tombo": f"T-{uuid.uuid4().hex[:8]}"}).json()

    t_retirada = datetime(2025, 5, 10, 10, 0, 0)
    client.post("/emprestimos", json={
        "usuario_id": u["id"],
        "exemplar_id": ex["id"],
        "data_retirada": t_retirada.isoformat()
    })

    # Consulta com período que engloba
    rel_ok = client.get("/relatorios/livros-mais-emprestados?data_inicio=2025-05-01T00:00:00&data_fim=2025-05-31T23:59:59").json()
    assert len(rel_ok) == 1
    assert rel_ok[0]["livro_id"] == l["id"]

    # Consulta com período fora
    rel_fora = client.get("/relatorios/livros-mais-emprestados?data_inicio=2026-01-01T00:00:00&data_fim=2026-01-31T23:59:59").json()
    assert len(rel_fora) == 0


def test_root_endpoint(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "online"
