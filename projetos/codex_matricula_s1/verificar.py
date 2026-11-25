from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

import banco
import main
import matriculas

with TemporaryDirectory() as tmp:
    banco.BANCO = Path(tmp) / "teste.sqlite3"
    instante = datetime(2026, 1, 1, tzinfo=UTC)
    main.agora = matriculas.agora = lambda: instante
    with TestClient(main.app) as api:
        def requisitar(metodo, rota, status, dados=None):
            resp = api.request(metodo, rota, json=dados)
            assert resp.status_code == status, (metodo, rota, resp.status_code, resp.text)
            return resp.json() if resp.content else None

        def post(rota, dados=None, status=201):
            return requisitar("POST", rota, status, dados)

        def get(rota):
            return requisitar("GET", rota, 200)

        def aluno(numero, categoria="graduacao", situacao="ativo"):
            return post("/alunos", dict(nome=f"Aluno {numero}", matricula=str(numero),
                        email=f"a{numero}@uni.edu", categoria=categoria, situacao=situacao))["id"]

        def disciplina(codigo, creditos=4):
            return post("/disciplinas", dict(codigo=codigo, nome=codigo, creditos=creditos,
                                             carga_horaria=60, departamento="Exatas"))["id"]

        def turma(d, vagas=10, inicio="08:00", fim="09:00", semestre="2026-1"):
            return post("/turmas", dict(disciplina_id=d, semestre=semestre, professor="Ana",
                        vagas=vagas, horario=[dict(dia="seg", inicio=inicio, fim=fim)]))["id"]

        def matricular(a, t, status=201):
            return post("/matriculas", dict(aluno_id=a, turma_id=t), status)

        def acao(m, nome, status=200):
            return post(f"/matriculas/{m['id']}/{nome}", status=status)

        def historico(a, d, situacao):
            return post(f"/alunos/{a}/historico", dict(disciplina_id=d, semestre="2025-2", situacao=situacao))

        d = disciplina("MAT")
        t = turma(d, vagas=1)
        titular, especial, grad, pos, segundo_pos = aluno(1), aluno(2, "especial"), aluno(3), aluno(4, "pos"), aluno(5, "pos")
        m1 = matricular(titular, t)
        me = matricular(especial, t)
        mg = matricular(grad, t)
        mp = matricular(pos, t)
        mp2 = matricular(segundo_pos, t)
        assert m1["estado"] == "confirmada" and me["estado"] == "lista_de_espera"
        rota = f"/turmas/{t}/lista-de-espera"
        assert [m["id"] for m in get(rota)] == [m["id"] for m in (mp, mp2, mg, me)]
        acao(mp, "confirmar", 409)
        acao(m1, "cancelar")
        assert get(rota)[0]["oferta_expira_em"] == (instante + timedelta(hours=48)).isoformat()
        instante += timedelta(hours=48)
        acao(mp, "confirmar", 409)
        assert get(f"/alunos/{pos}/matriculas")[0]["estado"] == "cancelada"
        assert get(rota)[0]["id"] == mp2["id"]
        assert acao(mp2, "confirmar")["estado"] == "confirmada"

        pre = disciplina("PRE")
        post(f"/disciplinas/{d}/pre-requisitos", {"disciplina_exigida_id": pre})
        post(f"/disciplinas/{pre}/pre-requisitos", {"disciplina_exigida_id": d}, 409)
        a = aluno(6)
        t2 = turma(d)
        matricular(a, t2, 409)
        historico(a, pre, "aprovado")
        mat = matricular(a, t2)
        matricular(a, turma(pre), 409)
        instante += timedelta(days=15, seconds=1)
        acao(mat, "trancar", 409)
        acao(mat, "cancelar")
        assert get(f"/alunos/{a}/historico")[-1]["motivo"] == "falta"
        historico(a, d, "reprovado")
        historico(a, d, "reprovado")
        matricular(a, t2, 409)

        for i, categoria, credito, dias in [(10, "graduacao", 28, 15), (11, "pos", 16, 30), (12, "especial", 8, 7)]:
            estudante = aluno(i, categoria)
            maximo = disciplina(f"MAX{i}", credito)
            outra = turma(pre, inicio="09:00", fim="10:00")
            unica = turma(maximo)
            m = matricular(estudante, unica)
            matricular(estudante, outra, 409)
            instante += timedelta(days=dias)
            acao(m, "cancelar")
            assert not get(f"/alunos/{estudante}/historico")
            m = matricular(estudante, unica)
            instante += timedelta(days=dias, seconds=1)
            acao(m, "cancelar")
            assert get(f"/alunos/{estudante}/historico")[0]["motivo"] == "falta"

        a = aluno(20)
        d3 = disciplina("TR")
        for _ in range(2):
            acao(matricular(a, turma(d3)), "trancar")
        acao(matricular(a, turma(d3)), "trancar", 409)
        restante = matricular(a, turma(pre, inicio="09:00", fim="10:00"))
        terceira = matricular(a, turma(disciplina("TR3"), inicio="10:00", fim="11:00"))
        acao(terceira, "trancar")
        assert get(f"/alunos/{a}")["situacao"] == "trancado"
        assert next(m for m in get(f"/alunos/{a}/matriculas") if m["id"] == restante["id"])["estado"] == "cancelada"
        matricular(a, t2, 409)

        for i, categoria, limite in [(21, "pos", 1), (22, "especial", 0)]:
            estudante = aluno(i, categoria)
            for _ in range(limite):
                acao(matricular(estudante, turma(d3)), "trancar")
            acao(matricular(estudante, turma(d3)), "trancar", 409)

        cheia = turma(pre, vagas=5, semestre="2026-2")
        pequena = turma(pre, vagas=4, semestre="2026-2", inicio="09:00", fim="10:00")
        for i in range(30, 35):
            estudante = aluno(i)
            matricular(estudante, cheia)
            matricular(estudante, pequena)
        resultado = post("/semestres/2026-2/encerrar-matriculas", status=200)
        assert resultado["turmas_canceladas"] == [pequena]
        assert get(f"/turmas/{cheia}")["estado"] == "lotada"
        assert get(f"/turmas/{pequena}")["estado"] == "cancelada"
        assert get(f"/alunos/{estudante}/matriculas")[-1]["estado"] == "cancelada"
        assert not get(f"/turmas/{pequena}/lista-de-espera")
        assert get("/relatorios/disciplinas-mais-procuradas?semestre=2026-2")[0]["solicitacoes"] == 10
        assert get("/relatorios/ocupacao-turmas?semestre=2026-2")[0]["turmas"][0]["taxa_ocupacao"] == 1
        assert next(r for r in get("/relatorios/taxa-reprovacao") if r["codigo"] == "MAT")["reprovacoes"] == 3
        post("/alunos", {"email": "invalido"}, 422)
        requisitar("DELETE", f"/disciplinas/{pre}", 409)
        requisitar("DELETE", "/alunos/9999", 404)
        livre = aluno(99)
        requisitar("DELETE", f"/alunos/{livre}", 204)
        disputada = turma(pre, vagas=1)
        concorrentes = [aluno(100), aluno(101)]
        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(lambda estudante: matricular(estudante, disputada), concorrentes))
        assert sorted(m["estado"] for m in resultados) == ["confirmada", "lista_de_espera"]
        print("Verificação dos fluxos REST concluída.")
