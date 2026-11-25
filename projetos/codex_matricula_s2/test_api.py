import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


class MatriculasTest(unittest.TestCase):
    def setUp(self):
        pasta = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"MATRICULAS_DB": str(Path(pasta) / "teste.sqlite3")}))
        self.cliente = self.enterContext(TestClient(app))
        self.instante = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.enterContext(patch("servico.agora", side_effect=lambda: self.instante.isoformat()))

    def post(self, rota, dados=None, status=201):
        resposta = self.cliente.post(rota, json=dados)
        self.assertEqual(resposta.status_code, status, resposta.text)
        return resposta.json()

    def get(self, rota):
        resposta = self.cliente.get(rota)
        self.assertEqual(resposta.status_code, 200, resposta.text)
        return resposta.json()

    def aluno(self, numero, categoria="graduacao"):
        return self.post("/alunos", {
            "nome": f"Aluno {numero}", "matricula": str(numero),
            "email": f"a{numero}@exemplo.edu", "categoria": categoria,
        })["id"]

    def turma(self, codigo, vagas=10, dia=1, creditos=4):
        disciplina = self.post("/disciplinas", {
            "nome": codigo, "codigo": codigo, "creditos": creditos,
            "departamento": "Computacao", "carga_horaria": 60,
        })["id"]
        return self.post("/turmas", {
            "disciplina_id": disciplina, "semestre": "2026.1", "professor": "Docente",
            "vagas": vagas, "horario": {"dia_semana": dia, "inicio": "08:00", "fim": "10:00"},
        })

    def solicitar(self, aluno, turma, status=201):
        return self.post("/matriculas", {"aluno_id": aluno, "turma_id": turma["id"]}, status)

    def acao(self, pedido, acao, status=200):
        return self.post(f"/matriculas/{pedido['id']}/{acao}", status=status)

    def historico(self, aluno, turma, situacao):
        return self.post(f"/alunos/{aluno}/historico", {
            "disciplina_id": turma["disciplina_id"], "semestre": "2025.2", "situacao": situacao,
        })

    def test_prioridade_desempate_e_expiracao_em_48_horas(self):
        turma = self.turma("A", vagas=1)
        titular = self.solicitar(self.aluno(1), turma)
        self.acao(titular, "confirmar")
        espera = [self.solicitar(self.aluno(i, categoria), turma) for i, categoria in
                  enumerate(["especial", "graduacao", "pos", "pos"], 2)]
        rota = f"/turmas/{turma['id']}/lista-de-espera"
        self.assertEqual([m["id"] for m in self.get(rota)["fila"]],
                         [espera[i]["id"] for i in (2, 3, 1, 0)])
        self.acao(titular, "cancelar")
        oferta = self.get(rota)["ofertas"][0]
        self.assertEqual(oferta["id"], espera[2]["id"])
        self.assertEqual(datetime.fromisoformat(oferta["prazo_confirmacao"]) - self.instante,
                         timedelta(hours=48))
        self.instante += timedelta(hours=48)
        self.acao(oferta, "confirmar", 409)
        self.assertEqual(self.get(rota)["ofertas"][0]["id"], espera[3]["id"])
        self.acao(espera[3], "confirmar")

    def test_pre_requisitos_reprovacoes_creditos_e_horario(self):
        aluno = self.aluno(1, "especial")
        base = self.turma("BASE")
        avancada = self.turma("AV", creditos=8)
        conflito = self.turma("CON", creditos=1)
        self.post(f"/disciplinas/{avancada['disciplina_id']}/pre-requisitos",
                  {"exigida_id": base["disciplina_id"]})
        self.solicitar(aluno, avancada, 409)
        self.historico(aluno, base, "aprovado")
        for _ in range(3):
            self.historico(aluno, base, "reprovado")
        self.solicitar(aluno, base, 409)
        pedido = self.solicitar(aluno, avancada)
        self.acao(pedido, "confirmar")
        self.assertIn("creditos", self.solicitar(aluno, conflito, 409)["detail"])
        outro = self.aluno(2)
        self.acao(self.solicitar(outro, conflito), "confirmar")
        self.historico(outro, base, "aprovado")
        self.assertIn("Horario", self.solicitar(outro, avancada, 409)["detail"])
        self.acao(pedido, "trancar", 409)
        self.instante += timedelta(days=7, seconds=1)
        self.acao(pedido, "cancelar")
        self.assertEqual(self.get(f"/alunos/{aluno}/historico")[-1]["motivo"], "falta")

    def test_tres_trancamentos_cancelam_matriculas_e_liberam_vaga(self):
        aluno = self.aluno(1)
        turmas = [self.turma(str(i), vagas=1, dia=i) for i in range(1, 5)]
        pedidos = [self.solicitar(aluno, turma) for turma in turmas]
        for pedido in pedidos:
            self.acao(pedido, "confirmar")
        espera = self.solicitar(self.aluno(2), turmas[-1])
        self.instante += timedelta(days=15)
        for pedido in pedidos[:3]:
            self.acao(pedido, "trancar")
        self.assertEqual(self.get(f"/alunos/{aluno}")["situacao"], "trancado")
        self.assertEqual(self.get(f"/alunos/{aluno}/matriculas")[-1]["estado"], "cancelada")
        self.assertEqual(self.get(f"/turmas/{turmas[-1]['id']}/lista-de-espera")["ofertas"][0]["id"],
                         espera["id"])

    def test_fechamento_e_relatorios(self):
        turma = self.turma("A")
        pequena = self.turma("B", vagas=4)
        for i in range(1, 6):
            aluno = self.aluno(i)
            self.acao(self.solicitar(aluno, turma), "confirmar")
        outro = self.aluno(6)
        self.solicitar(outro, pequena)
        self.historico(outro, turma, "reprovado")
        self.historico(outro, turma, "aprovado")
        for item, estado in ((turma, "aberta"), (pequena, "cancelada")):
            fechamento = self.post(f"/turmas/{item['id']}/encerrar-periodo-matricula", status=200)
            self.assertEqual(fechamento["estado"], estado)
            self.assertTrue(fechamento["periodo_encerrado"])
        self.solicitar(outro, turma, 409)
        self.assertEqual(self.get(f"/alunos/{outro}/matriculas")[0]["estado"], "cancelada")
        self.assertEqual(self.get("/relatorios/disciplinas-mais-procuradas?semestre=2026.1")[0]["solicitacoes"], 5)
        self.assertEqual(self.get("/relatorios/taxa-reprovacao")[0]["taxa_percentual"], 50)
        self.assertEqual(self.get("/relatorios/ocupacao-turmas")[0]["ocupacao_percentual"], 50)


if __name__ == "__main__":
    unittest.main()
