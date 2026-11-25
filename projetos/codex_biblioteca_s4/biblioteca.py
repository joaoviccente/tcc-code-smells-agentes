import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException


# Limite, prazo em dias, renovações, tarifa diária e teto em centavos.
POLITICAS = {
    "aluno": (3, 7, 2, 100, 3000),
    "professor": (8, 30, 4, 50, 5000),
    "visitante": (1, 3, 0, 200, 2000),
}


def conflito(mensagem):
    raise HTTPException(status_code=409, detail=mensagem)


class Biblioteca:
    def __init__(self, db, agora):
        self.db = db
        self.agora = agora
        self.hoje = agora.date()

    def executar(self, sql, *params):
        return self.db.execute(sql, params)

    def linhas(self, sql, *params):
        return [dict(row) for row in self.executar(sql, *params)]

    def um(self, sql, *params):
        row = self.executar(sql, *params).fetchone()
        return dict(row) if row else None

    def obter(self, tabela, id):
        registro = self.um(f"SELECT * FROM {tabela} WHERE id = ?", id)
        if registro is None:
            raise HTTPException(status_code=404, detail="Registro não encontrado.")
        return registro

    def inserir(self, tabela, **dados):
        colunas = ", ".join(dados)
        valores = ", ".join("?" for _ in dados)
        return self.executar(
            f"INSERT INTO {tabela} ({colunas}) VALUES ({valores})", *dados.values()
        ).lastrowid

    def atualizar(self, tabela, id, **dados):
        campos = ", ".join(f"{campo} = ?" for campo in dados)
        self.executar(f"UPDATE {tabela} SET {campos} WHERE id = ?", *dados.values(), id)

    def distribuir(self, livro_id, desde):
        exemplares = self.linhas(
            "SELECT id FROM exemplares WHERE livro_id = ? AND estado = 'disponivel' ORDER BY id",
            livro_id,
        )
        fila = self.linhas(
            "SELECT id FROM reservas WHERE livro_id = ? AND estado = 'aguardando' ORDER BY id",
            livro_id,
        )
        for exemplar, reserva in zip(exemplares, fila):
            self.atualizar("exemplares", exemplar["id"], estado="reservado")
            self.atualizar(
                "reservas", reserva["id"], estado="disponivel", exemplar_id=exemplar["id"],
                disponivel_ate=(desde + timedelta(hours=48)).isoformat(),
            )

    def liberar_reserva(self, reserva, estado):
        self.atualizar("reservas", reserva["id"], estado=estado, exemplar_id=None)
        if reserva["exemplar_id"] is not None:
            self.atualizar("exemplares", reserva["exemplar_id"], estado="disponivel")

    def cancelar_fila(self, livro_id):
        for reserva in self.linhas(
            "SELECT * FROM reservas WHERE livro_id = ? AND estado IN ('aguardando','disponivel')",
            livro_id,
        ):
            self.liberar_reserva(reserva, "cancelada")

    def apos_baixa(self, livro_id, era_disponivel=False):
        estados = {r["estado"] for r in self.linhas(
            "SELECT DISTINCT estado FROM exemplares WHERE livro_id = ?", livro_id
        )}
        sem_exemplar = not estados.intersection({"disponivel", "emprestado", "reservado"})
        if sem_exemplar or (era_disponivel and "disponivel" not in estados):
            self.cancelar_fila(livro_id)

    def fila(self, livro_id):
        reservas = self.linhas(
            "SELECT * FROM reservas WHERE livro_id = ? AND estado IN ('aguardando','disponivel') ORDER BY id",
            livro_id,
        )
        for posicao, reserva in enumerate(reservas, start=1):
            reserva["posicao"] = posicao
        return reservas

    def registrar_atraso(self, emprestimo, dias):
        if dias <= 0:
            return
        categoria = emprestimo["categoria"]
        _, _, _, diaria, teto = POLITICAS[categoria]
        valor = teto if emprestimo["data_devolucao"] and dias > 60 else min(dias * diaria, teto)
        multa = self.um("SELECT * FROM multas WHERE emprestimo_id = ?", emprestimo["id"])
        pago = multa["pago_centavos"] if multa else 0
        if categoria == "professor" and dias <= 2:
            estado = "perdoada"
        else:
            estado = "paga" if pago >= valor else "aberta"
        if multa:
            self.atualizar("multas", multa["id"], valor_centavos=valor, estado=estado)
        else:
            self.inserir("multas", emprestimo_id=emprestimo["id"], valor_centavos=valor, estado=estado)

        if dias > 15:
            limite = (self.hoje + timedelta(days=2 * dias)).isoformat()
            self.executar(
                """UPDATE usuarios SET situacao = 'suspenso', suspenso_ate = ?
                   WHERE id = ? AND (situacao = 'ativo' OR suspenso_ate < ?)""",
                limite, emprestimo["usuario_id"], limite,
            )

    def sincronizar(self):
        while reserva := self.um(
            """SELECT * FROM reservas WHERE estado = 'disponivel' AND disponivel_ate <= ?
               ORDER BY disponivel_ate, id LIMIT 1""",
            self.agora.isoformat(),
        ):
            self.liberar_reserva(reserva, "expirada")
            self.distribuir(reserva["livro_id"], datetime.fromisoformat(reserva["disponivel_ate"]))

        self.executar(
            """UPDATE usuarios SET situacao = 'ativo', suspenso_ate = NULL
               WHERE suspenso_ate <= ?""", self.hoje.isoformat()
        )
        for emprestimo in self.linhas(
            "SELECT * FROM emprestimos WHERE data_devolucao IS NULL AND data_prevista < ?",
            self.hoje.isoformat(),
        ):
            dias = (self.hoje - date.fromisoformat(emprestimo["data_prevista"])).days
            self.atualizar("emprestimos", emprestimo["id"], estado="atrasado", dias_atraso=dias)
            self.registrar_atraso(emprestimo, dias)


@contextmanager
def transacao(caminho, relogio):
    db = sqlite3.connect(caminho, timeout=10, check_same_thread=False)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("BEGIN IMMEDIATE")
        biblioteca = Biblioteca(db, relogio())
        biblioteca.sincronizar()
        db.execute("SAVEPOINT operacao")
        try:
            yield biblioteca
        except (HTTPException, sqlite3.IntegrityError) as erro:
            db.execute("ROLLBACK TO operacao")
            db.commit()
            if isinstance(erro, sqlite3.IntegrityError):
                conflito("O registro está duplicado ou possui vínculos que impedem a operação.")
            raise
        db.commit()
    finally:
        db.close()


def inicializar(caminho):
    with sqlite3.connect(caminho) as db:
        db.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8-sig"))
