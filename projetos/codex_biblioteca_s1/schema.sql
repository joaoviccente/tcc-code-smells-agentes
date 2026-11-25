CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    matricula TEXT NOT NULL COLLATE NOCASE UNIQUE,
    categoria TEXT NOT NULL CHECK (categoria IN ('aluno','professor','visitante')),
    situacao TEXT NOT NULL CHECK (situacao IN ('ativo','suspenso'))
);

CREATE TABLE IF NOT EXISTS livros (
    id INTEGER PRIMARY KEY,
    titulo TEXT NOT NULL,
    autor TEXT NOT NULL,
    isbn TEXT NOT NULL UNIQUE,
    ano INTEGER NOT NULL CHECK (ano BETWEEN 1 AND 9999),
    area_conhecimento TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exemplares (
    id INTEGER PRIMARY KEY,
    livro_id INTEGER NOT NULL REFERENCES livros(id),
    codigo_tombo TEXT NOT NULL COLLATE NOCASE UNIQUE,
    estado TEXT NOT NULL CHECK (estado IN ('disponivel','emprestado','reservado','em_reparo','baixado'))
);

CREATE TABLE IF NOT EXISTS emprestimos (
    id INTEGER PRIMARY KEY,
    exemplar_id INTEGER NOT NULL REFERENCES exemplares(id),
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    categoria TEXT NOT NULL CHECK (categoria IN ('aluno','professor','visitante')),
    data_retirada TEXT NOT NULL,
    data_prevista TEXT NOT NULL,
    data_devolucao TEXT,
    estado TEXT NOT NULL CHECK (estado IN ('ativo','devolvido','atrasado')),
    numero_renovacoes INTEGER NOT NULL DEFAULT 0,
    dias_atraso INTEGER NOT NULL DEFAULT 0,
    suspenso_ate TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS emprestimo_em_aberto
    ON emprestimos(exemplar_id) WHERE data_devolucao IS NULL;
CREATE INDEX IF NOT EXISTS emprestimos_usuario ON emprestimos(usuario_id);
CREATE INDEX IF NOT EXISTS emprestimos_retirada ON emprestimos(data_retirada);

CREATE TABLE IF NOT EXISTS reservas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    livro_id INTEGER NOT NULL REFERENCES livros(id),
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    data TEXT NOT NULL,
    estado TEXT NOT NULL CHECK (estado IN ('aguardando','disponivel','expirada','cancelada')),
    exemplar_id INTEGER REFERENCES exemplares(id),
    expira_em TEXT,
    CHECK (
        (estado = 'disponivel' AND exemplar_id IS NOT NULL AND expira_em IS NOT NULL)
        OR (estado <> 'disponivel' AND exemplar_id IS NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS reserva_em_aberto
    ON reservas(livro_id, usuario_id) WHERE estado IN ('aguardando','disponivel');
CREATE UNIQUE INDEX IF NOT EXISTS reserva_exemplar ON reservas(exemplar_id);
CREATE INDEX IF NOT EXISTS reservas_fila ON reservas(livro_id, id);

CREATE TABLE IF NOT EXISTS multas (
    id INTEGER PRIMARY KEY,
    emprestimo_id INTEGER NOT NULL UNIQUE REFERENCES emprestimos(id),
    valor_centavos INTEGER NOT NULL CHECK (valor_centavos > 0),
    pago_centavos INTEGER NOT NULL DEFAULT 0 CHECK (pago_centavos >= 0),
    estado TEXT NOT NULL CHECK (estado IN ('aberta','paga','perdoada'))
);
