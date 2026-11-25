import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException


@dataclass(frozen=True)
class Politica:
    saque_diario: int
    transferencia: int
    mensalidade: int
    franquia: int | None
    juros: int


POLITICAS = {
    "comum": Politica(100_000, 500_000, 3_000, 3, 8),
    "premium": Politica(500_000, 5_000_000, 0, None, 5),
    "empresarial": Politica(2_000_000, 20_000_000, 12_000, 50, 3),
}


def agora():
    return datetime.now(timezone.utc)


def centavos(valor):
    return int(valor * 100)


def reais(valor):
    return f"{Decimal(valor) / 100:.2f}"


def conflito(mensagem):
    raise HTTPException(409, mensagem)


def obter(db, tabela, id):
    registro = db.execute(f"SELECT * FROM {tabela} WHERE id = ?", (id,)).fetchone()
    if registro is None:
        raise HTTPException(404, "Registro inexistente")
    return registro


def publicar(registro):
    dados = dict(registro)
    for campo in ("valor", "valor_base", "saldo", "limite", "limite_credito"):
        if campo in dados:
            dados[campo] = reais(dados[campo])
    dados.pop("usa_franquia", None)
    return dados


def listar(db, sql, parametros=()):
    return [publicar(registro) for registro in db.execute(sql, parametros)]


def saldo(db, conta_id, variacao, instante):
    conta = obter(db, "contas", conta_id)
    if conta["estado"] == "encerrada":
        conflito("Conta encerrada")
    novo = conta["saldo"] + variacao
    if novo < -conta["limite_credito"]:
        conflito("Saldo e limite de credito insuficientes")
    negativa = (conta["negativa_desde"] or instante.isoformat()) if novo < 0 else None
    db.execute("UPDATE contas SET saldo = ?, negativa_desde = ? WHERE id = ?",
               (novo, negativa, conta_id))


def exigir_ativa(conta, cliente):
    if conta["estado"] != "ativa" or cliente["situacao"] != "ativo":
        conflito("A operacao exige conta e cliente ativos")


def registrar(db, conta, tipo, valor, instante, destino=None, original=None, franquia=False):
    return db.execute("""
        INSERT INTO transacoes
        (conta_id, destino_id, tipo, valor, data, estado, original_id, usa_franquia)
        VALUES (?, ?, ?, ?, ?, 'efetivada', ?, ?)
    """, (conta, destino, tipo, valor, instante.isoformat(), original, franquia)).lastrowid


def movimentar(db, tipo, dados, instante):
    origem = obter(db, "contas", dados.conta_id)
    cliente = obter(db, "clientes", origem["cliente_id"])
    valor = centavos(dados.valor)
    politica = POLITICAS[cliente["categoria"]]
    destino_id = None
    franquia = False
    if tipo == "deposito":
        saldo(db, origem["id"], valor, instante)
    else:
        exigir_ativa(origem, cliente)
        if tipo == "saque":
            total = db.execute("""
                SELECT COALESCE(SUM(valor), 0) FROM transacoes
                WHERE conta_id IN (SELECT id FROM contas WHERE cliente_id = ?)
                AND tipo = 'saque' AND estado = 'efetivada' AND substr(data, 1, 10) = ?
            """, (cliente["id"], instante.date().isoformat())).fetchone()[0]
            if total + valor > politica.saque_diario:
                conflito("Limite diario de saque excedido")
        else:
            destino_id = dados.destino_id
            if destino_id == origem["id"]:
                conflito("As contas da transferencia devem ser diferentes")
            destino = obter(db, "contas", destino_id)
            if destino["estado"] == "encerrada":
                conflito("Conta de destino encerrada")
            if valor > politica.transferencia:
                conflito("Limite por transferencia excedido")
            franquia = destino["cliente_id"] != cliente["id"]
            saldo(db, destino_id, valor, instante)
        saldo(db, origem["id"], -valor, instante)
    id = registrar(db, origem["id"], tipo, valor, instante, destino_id, franquia=franquia)
    if franquia and politica.franquia is not None:
        competencia = instante.strftime("%Y-%m")
        total = db.execute("""
            SELECT COUNT(*) FROM transacoes t JOIN contas c ON c.id = t.conta_id
            WHERE c.cliente_id = ? AND t.usa_franquia = 1 AND t.estado = 'efetivada'
            AND substr(t.data, 1, 7) = ?
        """, (cliente["id"], competencia)).fetchone()[0]
        if total > politica.franquia:
            db.execute("""
                INSERT INTO tarifas
                (conta_id, transacao_id, tipo, competencia, categoria, valor, estado)
                VALUES (?, ?, 'transferencia', ?, ?, ?, 'pendente')
            """, (origem["id"], id, competencia, cliente["categoria"], TARIFA_TRANSFERENCIA))
    cobrar_pendentes(db, instante)
    return publicar(obter(db, "transacoes", id))


def tarifa_transferencia():
    valor = Decimal(os.getenv("BANCO_TARIFA_TRANSFERENCIA", "10.00"))
    if (not valor.is_finite() or not 0 < valor <= Decimal("999999999999.99")
            or valor != valor.quantize(Decimal("0.01"))):
        raise ValueError("A tarifa de transferencia deve ser positiva e ter ate duas casas decimais")
    return centavos(valor)


TARIFA_TRANSFERENCIA = tarifa_transferencia()


def estornar(db, id, instante):
    original = obter(db, "transacoes", id)
    if original["estado"] != "efetivada" or original["tipo"] == "estorno":
        conflito("Transacao indisponivel para estorno")
    if instante - datetime.fromisoformat(original["data"]) > timedelta(hours=24):
        conflito("Prazo de 24 horas para estorno expirado")
    conta, destino, valor = original["conta_id"], original["destino_id"], original["valor"]
    tarifa = db.execute("SELECT * FROM tarifas WHERE transacao_id = ?", (id,)).fetchone()
    reembolso = 0
    if tarifa:
        if tarifa["estado"] == "cobrada":
            reembolso = tarifa["valor"]
        db.execute("UPDATE tarifas SET estado = 'isenta' WHERE id = ?", (tarifa["id"],))
    variacao = -valor if original["tipo"] == "deposito" else valor
    saldo(db, conta, variacao + reembolso, instante)
    if destino is not None:
        saldo(db, destino, -valor, instante)
    db.execute("UPDATE transacoes SET estado = 'estornada' WHERE id = ?", (id,))
    novo_id = registrar(db, conta, "estorno", valor, instante, destino, id)
    cobrar_pendentes(db, instante)
    return publicar(obter(db, "transacoes", novo_id))


def cobrar_pendentes(db, instante):
    tarifas = db.execute("SELECT * FROM tarifas WHERE estado = 'pendente' ORDER BY id").fetchall()
    for tarifa in tarifas:
        conta = obter(db, "contas", tarifa["conta_id"])
        if conta["estado"] == "encerrada" or conta["saldo"] + conta["limite_credito"] < tarifa["valor"]:
            continue
        saldo(db, conta["id"], -tarifa["valor"], instante)
        db.execute("UPDATE tarifas SET estado = 'cobrada', cobrada_em = ? WHERE id = ?",
                   (instante.isoformat(), tarifa["id"]))


def mensalidades(db, instante):
    atual = instante.strftime("%Y-%m")
    contas = db.execute("""
        SELECT c.*, cl.categoria FROM contas c JOIN clientes cl ON cl.id = c.cliente_id
        WHERE c.estado != 'encerrada'
    """)
    for conta in contas.fetchall():
        ultima = db.execute("""
            SELECT MAX(competencia) FROM tarifas WHERE conta_id = ? AND tipo = 'mensal'
        """, (conta["id"],)).fetchone()[0]
        competencia = ultima or conta["criada_em"][:7]
        if ultima:
            competencia = proximo_mes(competencia)
        valor = POLITICAS[conta["categoria"]].mensalidade
        while competencia < atual:
            db.execute("""
                INSERT INTO tarifas (conta_id, tipo, competencia, categoria, valor, estado)
                VALUES (?, 'mensal', ?, ?, ?, ?)
            """, (conta["id"], competencia, conta["categoria"], valor,
                  "pendente" if valor else "isenta"))
            competencia = proximo_mes(competencia)


def proximo_mes(competencia):
    ano, mes = map(int, competencia.split("-"))
    return f"{ano + (mes == 12):04d}-{mes % 12 + 1:02d}"


def atualizar_atrasos(db, instante):
    faturas = db.execute("""
        SELECT f.*, cl.categoria FROM faturas f
        JOIN cartoes ca ON ca.id = f.cartao_id
        JOIN contas co ON co.id = ca.conta_id
        JOIN clientes cl ON cl.id = co.cliente_id
        WHERE f.estado != 'paga' AND f.vencimento < ?
    """, (instante.date().isoformat(),)).fetchall()
    for fatura in faturas:
        vencimento = datetime.fromisoformat(fatura["vencimento"]).date()
        dias = (instante.date() - vencimento).days
        taxa = POLITICAS[fatura["categoria"]].juros
        juros = (Decimal(fatura["valor_base"]) * taxa * dias / 3000).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        db.execute("UPDATE faturas SET estado = 'atrasada', valor = ? WHERE id = ?",
                   (fatura["valor_base"] + int(juros), fatura["id"]))
        if dias >= 10:
            db.execute("UPDATE cartoes SET estado = 'bloqueado' WHERE id = ? AND estado = 'ativo'",
                       (fatura["cartao_id"],))


def manutencao(db, instante):
    mensalidades(db, instante)
    cobrar_pendentes(db, instante)
    atualizar_atrasos(db, instante)
    corte = (instante - timedelta(days=30)).isoformat()
    db.execute("""
        UPDATE clientes SET situacao = 'bloqueado'
        WHERE situacao = 'ativo' AND id IN (SELECT cliente_id FROM contas WHERE negativa_desde < ?)
    """, (corte,))
    db.execute("""
        UPDATE cartoes SET estado = 'bloqueado' WHERE estado = 'ativo' AND conta_id IN (
            SELECT id FROM contas WHERE cliente_id IN (
                SELECT cliente_id FROM contas WHERE negativa_desde < ?
            )
        )
    """, (corte,))


