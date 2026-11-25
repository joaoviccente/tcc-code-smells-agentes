from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from main import criar_app


def verificar(caminho):
    atual = datetime(2026, 1, 1, 10, tzinfo=timezone(timedelta(hours=-3)))
    with TestClient(criar_app(caminho, lambda: atual)) as api:
        def req(metodo, rota, status=200, **dados):
            resposta = api.request(metodo, rota, json=dados) if dados else api.request(metodo, rota)
            assert resposta.status_code == status, (rota, resposta.text)
            return resposta.json() if resposta.content else None

        def usuario(categoria, matricula):
            return req("POST", "/usuarios", 201, nome=matricula, email=f"{matricula}@example.org",
                       matricula=matricula, categoria=categoria)["id"]

        def livro(isbn):
            return req("POST", "/livros", 201, titulo="Livro", autor="Autor", isbn=isbn,
                       ano=2025, area_conhecimento="Matemática")["id"]

        def exemplar(livro_id, tombo):
            return req("POST", "/exemplares", 201, livro_id=livro_id, codigo_tombo=tombo)["id"]

        def emprestar(usuario_id, exemplar_id, status=201):
            return req("POST", "/emprestimos", status, usuario_id=usuario_id, exemplar_id=exemplar_id)

        def reservar(usuario_id, livro_id):
            return req("POST", "/reservas", 201, usuario_id=usuario_id, livro_id=livro_id)

        aluno, professor, visitante = (usuario(categoria, categoria) for categoria in
                                        ("aluno", "professor", "visitante"))
        obra = livro("978-0-306-40615-7")
        primeiro = exemplar(obra, "A")
        emprestimo = emprestar(aluno, primeiro)
        assert emprestimo["data_prevista"] == "2026-01-08"
        rota = f"/emprestimos/{emprestimo['id']}"
        reserva = reservar(professor, obra)
        assert reserva["estado"] == "aguardando"
        assert reservar(visitante, obra)["posicao"] == 2
        req("POST", rota + "/renovar", 409)
        req("POST", rota + "/devolver")
        assert req("GET", f"/livros/{obra}/reservas")[0]["estado"] == "disponivel"
        emprestar(visitante, primeiro, 409)
        atual += timedelta(hours=48)
        fila = req("GET", f"/livros/{obra}/reservas")
        assert len(fila) == 1 and fila[0]["usuario_id"] == visitante and fila[0]["estado"] == "disponivel"
        visita = emprestar(visitante, primeiro)
        rota_visita = f"/emprestimos/{visita['id']}"
        assert visita["data_prevista"] == "2026-01-06"
        req("POST", rota_visita + "/renovar", 409)
        atual += timedelta(days=64)
        req("POST", rota_visita + "/devolver")
        assert req("GET", f"/exemplares/{primeiro}")["estado"] == "baixado"
        multa = req("GET", f"/usuarios/{visitante}/multas")[0]
        assert multa["valor"] == 20 and multa["estado"] == "aberta"
        assert req("GET", f"/usuarios/{visitante}")["situacao"] == "suspenso"
        req("POST", f"/multas/{multa['id']}/pagar")
        assert req("GET", f"/usuarios/{visitante}/multas")[0]["estado"] == "paga"
        atual += timedelta(days=122)
        assert req("GET", f"/usuarios/{visitante}")["situacao"] == "ativo"

        segundo = exemplar(obra, "B")
        aula = emprestar(professor, segundo)
        prof_rota = f"/emprestimos/{aula['id']}"
        for renovacoes in range(1, 5):
            assert req("POST", prof_rota + "/renovar")["renovacoes"] == renovacoes
        req("POST", prof_rota + "/renovar", 409)
        atual += timedelta(days=152)
        assert req("GET", f"/usuarios/{professor}/multas")[0]["estado"] == "perdoada"
        atual += timedelta(days=1)
        assert req("GET", f"/usuarios/{professor}/multas")[0]["valor"] == 1.5
        req("POST", prof_rota + "/devolver")
        assert req("GET", "/relatorios/usuarios-com-mais-atrasos")[0]["total_atrasos"] == 1
        assert req("GET", "/relatorios/ocupacao-por-area")[0]["total_exemplares"] == 1
        req("GET", "/relatorios/livros-mais-emprestados?inicio=2026-12-31&fim=2026-01-01", 422)
        assert req("GET", "/relatorios/livros-mais-emprestados?inicio=2026-01-01&fim=2027-12-31")[0]["total_emprestimos"] == 3
        req("GET", "/openapi.json")
    with TestClient(criar_app(caminho, lambda: atual)) as api:
        assert len(api.get("/usuarios").json()) == 3


def test_fluxos_http_e_persistencia(tmp_path):
    verificar(tmp_path / "teste.db")


def test_limites_de_atraso(tmp_path):
    atual = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    with TestClient(criar_app(tmp_path / "limites.db", lambda: atual)) as api:
        usuario = api.post("/usuarios", json={
            "nome": "Professor", "email": "prof@example.org", "matricula": "P", "categoria": "professor",
        }).json()
        livro = api.post("/livros", json={
            "titulo": "Livro", "autor": "Autor", "isbn": "9780306406157", "ano": 2000,
            "area_conhecimento": "Ciências",
        }).json()
        ids = [
            api.post("/exemplares", json={"livro_id": livro["id"], "codigo_tombo": codigo}).json()["id"]
            for codigo in ("A", "B")
        ]
        emprestimos = [
            api.post("/emprestimos", json={"usuario_id": usuario["id"], "exemplar_id": id}).json()
            for id in ids
        ]
        atual += timedelta(days=45)
        assert api.get("/usuarios/1").json()["situacao"] == "ativo"
        atual += timedelta(days=1)
        assert api.get("/usuarios/1").json()["situacao"] == "suspenso"
        atual += timedelta(days=44)
        assert api.post(f"/emprestimos/{emprestimos[0]['id']}/devolver").status_code == 200
        assert api.get(f"/exemplares/{ids[0]}").json()["estado"] == "disponivel"
        atual += timedelta(days=1)
        assert api.post(f"/emprestimos/{emprestimos[1]['id']}/devolver").status_code == 200
        assert api.get(f"/exemplares/{ids[1]}").json()["estado"] == "baixado"
        assert [multa["valor"] for multa in api.get("/usuarios/1/multas").json()] == [30, 50]
