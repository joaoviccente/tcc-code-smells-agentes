from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from os import getenv
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Path as Parametro, Query, Response

from biblioteca import POLITICAS, Biblioteca, conflito, inicializar, transacao
from esquemas import Exemplar, Livro, NovaReserva, NovoEmprestimo, Periodo, Usuario


def agora_local():
    return datetime.now(timezone(timedelta(hours=-3)))


def criar_app(caminho=None, relogio=agora_local):
    caminho = caminho or getenv("BIBLIOTECA_DB") or Path(__file__).with_name("biblioteca.db")

    @asynccontextmanager
    async def lifespan(app):
        inicializar(caminho)
        yield

    api = FastAPI(title="Biblioteca Universitária", lifespan=lifespan)

    def sessao():
        with transacao(caminho, relogio) as biblioteca:
            yield biblioteca

    Banco = Annotated[Biblioteca, Depends(sessao, scope="function")]
    Identificador = Annotated[int, Parametro(gt=0)]

    @api.post("/usuarios", status_code=201)
    def criar_usuario(dados: Usuario, db: Banco):
        id = db.inserir("usuarios", **dados.model_dump(mode="json"))
        return db.obter("usuarios", id)

    @api.get("/usuarios")
    def listar_usuarios(db: Banco):
        return db.linhas("SELECT * FROM usuarios ORDER BY id")

    @api.get("/usuarios/{id}")
    def consultar_usuario(id: Identificador, db: Banco):
        return db.obter("usuarios", id)

    @api.put("/usuarios/{id}")
    def atualizar_usuario(id: Identificador, dados: Usuario, db: Banco):
        usuario = db.obter("usuarios", id)
        if usuario["suspenso_ate"] and dados.situacao == "ativo":
            conflito("A suspensão automática ainda está em vigor.")
        db.atualizar("usuarios", id, **dados.model_dump(mode="json"))
        return db.obter("usuarios", id)

    @api.delete("/usuarios/{id}", status_code=204)
    def excluir_usuario(id: Identificador, db: Banco):
        db.obter("usuarios", id)
        db.executar("DELETE FROM usuarios WHERE id = ?", id)
        return Response(status_code=204)

    @api.post("/livros", status_code=201)
    def criar_livro(dados: Livro, db: Banco):
        id = db.inserir("livros", **dados.model_dump(mode="json"))
        return db.obter("livros", id)

    @api.get("/livros")
    def listar_livros(db: Banco):
        return db.linhas("SELECT * FROM livros ORDER BY id")

    @api.get("/livros/{id}")
    def consultar_livro(id: Identificador, db: Banco):
        return db.obter("livros", id)

    @api.put("/livros/{id}")
    def atualizar_livro(id: Identificador, dados: Livro, db: Banco):
        db.obter("livros", id)
        db.atualizar("livros", id, **dados.model_dump(mode="json"))
        return db.obter("livros", id)

    @api.delete("/livros/{id}", status_code=204)
    def excluir_livro(id: Identificador, db: Banco):
        db.obter("livros", id)
        db.executar("DELETE FROM livros WHERE id = ?", id)
        return Response(status_code=204)

    @api.post("/exemplares", status_code=201)
    def criar_exemplar(dados: Exemplar, db: Banco):
        db.obter("livros", dados.livro_id)
        if dados.estado in {"reservado", "emprestado"}:
            conflito("O estado exige uma reserva ou um empréstimo.")
        id = db.inserir("exemplares", **dados.model_dump(mode="json"))
        db.distribuir(dados.livro_id, db.agora)
        return db.obter("exemplares", id)

    @api.get("/exemplares")
    def listar_exemplares(db: Banco):
        return db.linhas("SELECT * FROM exemplares ORDER BY id")

    @api.get("/exemplares/{id}")
    def consultar_exemplar(id: Identificador, db: Banco):
        return db.obter("exemplares", id)

    @api.put("/exemplares/{id}")
    def atualizar_exemplar(id: Identificador, dados: Exemplar, db: Banco):
        exemplar = db.obter("exemplares", id)
        db.obter("livros", dados.livro_id)
        estado = exemplar["estado"]
        if estado in {"emprestado", "reservado"} and (
            dados.estado != estado or dados.livro_id != exemplar["livro_id"]
        ):
            conflito("O exemplar está vinculado a uma operação em andamento.")
        if dados.estado in {"emprestado", "reservado"} and dados.estado != estado:
            conflito("O estado exige uma reserva ou um empréstimo.")
        if dados.livro_id != exemplar["livro_id"] and db.um(
            "SELECT id FROM emprestimos WHERE exemplar_id = ?", id
        ):
            conflito("O exemplar possui histórico de empréstimos.")
        db.atualizar("exemplares", id, **dados.model_dump(mode="json"))
        if dados.estado == "baixado" and estado != "baixado":
            db.apos_baixa(exemplar["livro_id"], estado == "disponivel")
        db.distribuir(dados.livro_id, db.agora)
        return db.obter("exemplares", id)

    @api.delete("/exemplares/{id}", status_code=204)
    def excluir_exemplar(id: Identificador, db: Banco):
        exemplar = db.obter("exemplares", id)
        db.executar("DELETE FROM exemplares WHERE id = ?", id)
        db.apos_baixa(exemplar["livro_id"], exemplar["estado"] == "disponivel")
        return Response(status_code=204)

    @api.post("/emprestimos", status_code=201)
    def criar_emprestimo(dados: NovoEmprestimo, db: Banco):
        usuario = db.obter("usuarios", dados.usuario_id)
        exemplar = db.obter("exemplares", dados.exemplar_id)
        limite, prazo, *_ = POLITICAS[usuario["categoria"]]
        if usuario["situacao"] != "ativo":
            conflito("O usuário está suspenso.")
        if db.um(
            """SELECT m.id FROM multas m JOIN emprestimos e ON e.id = m.emprestimo_id
               WHERE e.usuario_id = ? AND m.estado = 'aberta'""", usuario["id"],
        ):
            conflito("O usuário possui multa aberta.")
        ocupados = db.um(
            """SELECT COUNT(*) AS total FROM emprestimos
               WHERE usuario_id = ? AND data_devolucao IS NULL""", usuario["id"],
        )
        if ocupados["total"] >= limite:
            conflito("O usuário atingiu o limite de empréstimos.")
        if exemplar["estado"] == "reservado":
            reserva = db.um(
                "SELECT id FROM reservas WHERE exemplar_id = ? AND usuario_id = ? AND estado = 'disponivel'",
                exemplar["id"], usuario["id"],
            )
            if not reserva:
                conflito("O exemplar está reservado para outro usuário.")
            db.executar("DELETE FROM reservas WHERE id = ?", reserva["id"])
        elif exemplar["estado"] != "disponivel":
            conflito("O exemplar está indisponível para empréstimo.")
        id = db.inserir(
            "emprestimos", exemplar_id=exemplar["id"], usuario_id=usuario["id"],
            categoria=usuario["categoria"], data_retirada=db.hoje.isoformat(),
            data_prevista=(db.hoje + timedelta(days=prazo)).isoformat(), estado="ativo",
        )
        db.atualizar("exemplares", exemplar["id"], estado="emprestado")
        return db.obter("emprestimos", id)

    @api.post("/emprestimos/{id}/renovar")
    def renovar_emprestimo(id: Identificador, db: Banco):
        emprestimo = db.obter("emprestimos", id)
        exemplar = db.obter("exemplares", emprestimo["exemplar_id"])
        _, prazo, limite, *_ = POLITICAS[emprestimo["categoria"]]
        if emprestimo["estado"] != "ativo":
            conflito("Somente empréstimos ativos e em dia podem ser renovados.")
        if db.fila(exemplar["livro_id"]):
            conflito("O livro possui fila de reservas.")
        if emprestimo["renovacoes"] >= limite:
            conflito("O limite de renovações foi atingido.")
        vencimento = date.fromisoformat(emprestimo["data_prevista"]) + timedelta(days=prazo)
        db.atualizar(
            "emprestimos", id, data_prevista=vencimento.isoformat(), renovacoes=emprestimo["renovacoes"] + 1
        )
        return db.obter("emprestimos", id)

    @api.post("/emprestimos/{id}/devolver")
    def devolver_emprestimo(id: Identificador, db: Banco):
        emprestimo = db.obter("emprestimos", id)
        if emprestimo["data_devolucao"]:
            conflito("O empréstimo já foi devolvido.")
        exemplar = db.obter("exemplares", emprestimo["exemplar_id"])
        dias = emprestimo["dias_atraso"]
        emprestimo["data_devolucao"] = db.hoje.isoformat()
        db.atualizar("emprestimos", id, estado="devolvido", data_devolucao=emprestimo["data_devolucao"])
        db.registrar_atraso(emprestimo, dias)
        if dias > 60:
            db.atualizar("exemplares", exemplar["id"], estado="baixado")
            db.apos_baixa(exemplar["livro_id"])
        else:
            db.atualizar("exemplares", exemplar["id"], estado="disponivel")
            db.distribuir(exemplar["livro_id"], db.agora)
        return db.obter("emprestimos", id)

    @api.get("/usuarios/{id}/emprestimos")
    def listar_emprestimos(id: Identificador, db: Banco):
        db.obter("usuarios", id)
        return db.linhas("SELECT * FROM emprestimos WHERE usuario_id = ? ORDER BY id", id)

    @api.post("/reservas", status_code=201)
    def criar_reserva(dados: NovaReserva, db: Banco):
        db.obter("usuarios", dados.usuario_id)
        db.obter("livros", dados.livro_id)
        if not db.um(
            """SELECT id FROM exemplares WHERE livro_id = ?
               AND estado IN ('disponivel','emprestado','reservado')""", dados.livro_id,
        ):
            conflito("O livro não possui exemplar apto para reserva.")
        id = db.inserir(
            "reservas", **dados.model_dump(mode="json"), data=db.agora.isoformat(), estado="aguardando",
        )
        db.distribuir(dados.livro_id, db.agora)
        return next(reserva for reserva in db.fila(dados.livro_id) if reserva["id"] == id)

    @api.post("/reservas/{id}/cancelar")
    def cancelar_reserva(id: Identificador, db: Banco):
        reserva = db.obter("reservas", id)
        if reserva["estado"] not in {"aguardando", "disponivel"}:
            conflito("A reserva já foi encerrada.")
        db.liberar_reserva(reserva, "cancelada")
        db.distribuir(reserva["livro_id"], db.agora)
        return dict(db.obter("reservas", id), posicao=None)

    @api.get("/livros/{id}/reservas")
    def listar_fila(id: Identificador, db: Banco):
        db.obter("livros", id)
        return db.fila(id)

    def valores_multa(multa):
        return {
            "id": multa["id"],
            "emprestimo_id": multa["emprestimo_id"],
            "valor": multa["valor_centavos"] / 100,
            "saldo": (multa["valor_centavos"] - multa["pago_centavos"]) / 100
            if multa["estado"] == "aberta" else 0,
            "estado": multa["estado"],
        }

    @api.get("/usuarios/{id}/multas")
    def listar_multas(id: Identificador, db: Banco):
        db.obter("usuarios", id)
        return [
            valores_multa(multa) for multa in db.linhas(
                """SELECT m.* FROM multas m JOIN emprestimos e ON e.id = m.emprestimo_id
                   WHERE e.usuario_id = ? ORDER BY m.id""", id,
            )
        ]

    @api.post("/multas/{id}/pagar")
    def pagar_multa(id: Identificador, db: Banco):
        multa = db.obter("multas", id)
        if multa["estado"] == "perdoada":
            conflito("A multa foi perdoada.")
        if multa["estado"] == "aberta":
            db.atualizar("multas", id, pago_centavos=multa["valor_centavos"], estado="paga")
        return valores_multa(db.obter("multas", id))

    @api.get("/relatorios/livros-mais-emprestados")
    def livros_mais_emprestados(periodo: Annotated[Periodo, Query()], db: Banco):
        return db.linhas(
            """SELECT l.id AS livro_id, l.titulo, COUNT(*) AS total_emprestimos
               FROM emprestimos e JOIN exemplares x ON x.id = e.exemplar_id
               JOIN livros l ON l.id = x.livro_id
               WHERE e.data_retirada BETWEEN ? AND ?
               GROUP BY l.id ORDER BY total_emprestimos DESC, l.id""",
            periodo.inicio.isoformat(), periodo.fim.isoformat(),
        )

    @api.get("/relatorios/usuarios-com-mais-atrasos")
    def usuarios_com_mais_atrasos(db: Banco):
        return db.linhas(
            """SELECT u.id AS usuario_id, u.nome, COUNT(*) AS total_atrasos
               FROM emprestimos e JOIN usuarios u ON u.id = e.usuario_id
               WHERE e.dias_atraso > 0 GROUP BY u.id ORDER BY total_atrasos DESC, u.id"""
        )

    @api.get("/relatorios/ocupacao-por-area")
    def ocupacao_por_area(db: Banco):
        return db.linhas(
            """SELECT l.area_conhecimento, COUNT(x.id) AS total_exemplares,
                      SUM(CASE WHEN x.estado IN ('emprestado','reservado') THEN 1 ELSE 0 END) AS ocupados,
                      COALESCE(ROUND(100.0 * SUM(CASE WHEN x.estado IN ('emprestado','reservado')
                          THEN 1 ELSE 0 END) / NULLIF(COUNT(x.id), 0), 2), 0) AS taxa_ocupacao
               FROM livros l LEFT JOIN exemplares x ON x.livro_id = l.id
                   AND x.estado != 'baixado'
               GROUP BY l.area_conhecimento ORDER BY l.area_conhecimento"""
        )

    return api


app = criar_app()
