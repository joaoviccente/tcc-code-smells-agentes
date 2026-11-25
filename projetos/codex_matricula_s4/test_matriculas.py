import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


class MatriculasTest(unittest.TestCase):
    def setUp(self):
        pasta = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"MATRICULAS_DB": str(Path(pasta) / "teste.sqlite3")}))
        self.instante = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.enterContext(patch("regras.agora", side_effect=lambda: self.instante))
        self.api = self.enterContext(TestClient(app))
        self.sequencia = 0

    def post(self, rota, dados=None, status=201):
        resposta = self.api.post(rota, json=dados)
        self.assertEqual(resposta.status_code, status, resposta.text)
        return resposta.json()

    def aluno(self, categoria="graduacao"):
        self.sequencia += 1
        return self.post("/alunos", {"nome": "Aluno", "matricula": str(self.sequencia),
                                     "email": f"a{self.sequencia}@universidade.edu", "categoria": categoria})["id"]

    def turma(self, vagas=5, creditos=4, dia=1):
        self.sequencia += 1
        disciplina = self.post("/disciplinas", {"codigo": str(self.sequencia), "nome": "Disciplina",
                                               "creditos": creditos, "carga_horaria": 60, "departamento": "Exatas"})
        turma = self.post("/turmas", {"disciplina_id": disciplina["id"], "semestre": "2026.1", "professor": "Docente",
                                    "vagas": vagas, "horario": {"dia": dia, "inicio": "08:00", "fim": "10:00"}})
        return disciplina["id"], turma["id"]

    def solicitar(self, aluno, turma, status=201):
        return self.post("/matriculas", {"aluno_id": aluno, "turma_id": turma}, status=status)

    def acao(self, matricula, acao, status=200):
        return self.post(f"/matriculas/{matricula['id']}/{acao}", status=status)

    def historico(self, aluno, disciplina, situacao):
        return self.post(f"/alunos/{aluno}/historico", {"disciplina_id": disciplina, "semestre": "2025.2",
                                                       "situacao": situacao})

    def test_prioridade_fifo_e_expiracao(self):
        _, turma = self.turma(vagas=1)
        titular = self.solicitar(self.aluno(), turma)
        especial = self.solicitar(self.aluno("especial"), turma)
        primeiro = self.solicitar(self.aluno("pos"), turma)
        segundo = self.solicitar(self.aluno("pos"), turma)
        self.acao(titular, "cancelar")
        fila = self.api.get(f"/turmas/{turma}/lista-de-espera").json()
        self.assertEqual([item["id"] for item in fila["fila"]], [segundo["id"], especial["id"]])
        self.assertEqual(fila["ofertas"][0]["id"], primeiro["id"])
        self.instante += timedelta(hours=48)
        self.acao(primeiro, "confirmar", status=409)
        self.assertEqual(self.acao(segundo, "confirmar")["estado"], "confirmada")

    def test_pre_requisito_reprovacoes_creditos_e_horario(self):
        aluno = self.aluno("pos")
        origem, _ = self.turma()
        destino, turma = self.turma(creditos=16)
        self.post(f"/disciplinas/{destino}/pre-requisitos", {"exigida_id": origem})
        self.solicitar(aluno, turma, status=409)
        self.historico(aluno, origem, "aprovado")
        self.assertEqual(self.solicitar(aluno, turma)["estado"], "confirmada")
        _, extra = self.turma(dia=2)
        self.solicitar(aluno, extra, status=409)
        graduando = self.aluno()
        self.historico(graduando, origem, "aprovado")
        self.solicitar(graduando, turma)
        repetida, outra = self.turma()
        self.solicitar(graduando, outra, status=409)
        for _ in range(3):
            self.historico(aluno, repetida, "reprovado")
        self.assertIn("reprovacoes", self.solicitar(aluno, outra, status=409)["detail"])

    def test_trancamento_cascata_e_cancelamento_fora_do_prazo(self):
        aluno = self.aluno()
        matriculas = [self.solicitar(aluno, self.turma(dia=dia)[1]) for dia in range(1, 5)]
        for matricula in matriculas[:3]:
            self.acao(matricula, "trancar")
        self.assertEqual(self.api.get(f"/alunos/{aluno}").json()["situacao"], "trancado")
        registros = self.api.get(f"/alunos/{aluno}/matriculas").json()
        self.assertEqual(registros[-1]["estado"], "cancelada")

        especial = self.aluno("especial")
        _, turma = self.turma()
        matricula = self.solicitar(especial, turma)
        self.acao(matricula, "trancar", status=409)
        self.instante += timedelta(days=7, microseconds=1)
        self.acao(matricula, "cancelar")
        historico = self.api.get(f"/alunos/{especial}/historico").json()
        self.assertEqual((historico[0]["situacao"], historico[0]["motivo"]), ("reprovado", "falta"))

    def test_encerramento_pelo_minimo_e_relatorios(self):
        _, pequena = self.turma()
        _, grande = self.turma()
        for _ in range(4):
            self.solicitar(self.aluno(), pequena)
        for _ in range(5):
            self.solicitar(self.aluno(), grande)
        resultado = self.post("/periodos-matricula/2026.1/encerrar", status=200)
        self.assertEqual(resultado["turmas_canceladas"], [pequena])
        self.assertEqual(self.api.get(f"/turmas/{grande}").json()["estado"], "lotada")
        self.solicitar(self.aluno(), grande, status=409)
        ocupacao = self.api.get("/relatorios/ocupacao-turmas?semestre=2026.1").json()
        self.assertEqual(ocupacao[0]["taxa"], 1.0)
        procura = self.api.get("/relatorios/disciplinas-mais-procuradas?semestre=2026.1").json()
        self.assertEqual([item["solicitacoes"] for item in procura], [5, 4])
        self.assertEqual(self.api.get("/relatorios/taxa-reprovacao").status_code, 200)


if __name__ == "__main__":
    unittest.main()
