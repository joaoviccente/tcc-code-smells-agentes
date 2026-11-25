CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY, nome TEXT NOT NULL, cpf TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL, categoria TEXT NOT NULL, situacao TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contas (
    id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    numero TEXT NOT NULL UNIQUE, tipo TEXT NOT NULL, saldo INTEGER NOT NULL DEFAULT 0,
    limite_credito INTEGER NOT NULL, estado TEXT NOT NULL, negativo_desde TEXT,
    aberta_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cartoes (
    id INTEGER PRIMARY KEY, conta_id INTEGER NOT NULL REFERENCES contas(id),
    numero TEXT NOT NULL UNIQUE, limite INTEGER NOT NULL, estado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS faturas (
    id INTEGER PRIMARY KEY, cartao_id INTEGER NOT NULL REFERENCES cartoes(id),
    mes_referencia TEXT NOT NULL, vencimento TEXT NOT NULL, valor INTEGER NOT NULL,
    juros INTEGER NOT NULL DEFAULT 0, taxa_atraso INTEGER, estado TEXT NOT NULL,
    paga_em TEXT, UNIQUE(cartao_id, mes_referencia)
);
CREATE TABLE IF NOT EXISTS transacoes (
    id INTEGER PRIMARY KEY, conta_id INTEGER NOT NULL REFERENCES contas(id),
    destino_id INTEGER REFERENCES contas(id), tipo TEXT NOT NULL, valor INTEGER NOT NULL,
    data TEXT NOT NULL, dia TEXT NOT NULL, estado TEXT NOT NULL,
    original_id INTEGER UNIQUE REFERENCES transacoes(id)
);
CREATE TABLE IF NOT EXISTS tarifas (
    id INTEGER PRIMARY KEY, conta_id INTEGER NOT NULL REFERENCES contas(id),
    transacao_id INTEGER UNIQUE REFERENCES transacoes(id), tipo TEXT NOT NULL,
    valor INTEGER NOT NULL, estado TEXT NOT NULL, competencia TEXT NOT NULL,
    categoria TEXT NOT NULL, usa_franquia INTEGER NOT NULL DEFAULT 0, cobrada_em TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS tarifa_mensal ON tarifas(conta_id, competencia)
    WHERE tipo = 'mensal';
CREATE INDEX IF NOT EXISTS transacoes_conta_data ON transacoes(conta_id, data);
CREATE INDEX IF NOT EXISTS transacoes_destino ON transacoes(destino_id);
CREATE INDEX IF NOT EXISTS tarifas_conta_mes ON tarifas(conta_id, competencia);

