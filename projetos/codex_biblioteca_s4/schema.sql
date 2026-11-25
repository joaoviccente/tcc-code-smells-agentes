PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    matricula TEXT NOT NULL UNIQUE,
    categoria TEXT NOT NULL CHECK (categoria IN ('aluno','professor','visitante')),
    situacao TEXT NOT NULL CHECK (situacao IN ('ativo','suspenso')),
    suspenso_ate TEXT
);
CREATE TABLE IF NOT EXISTS livros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    autor TEXT NOT NULL,
    isbn TEXT NOT NULL UNIQUE,
    ano INTEGER NOT NULL,
    area_conhecimento TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exemplares (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    livro_id INTEGER NOT NULL REFERENCES livros(id),
    codigo_tombo TEXT NOT NULL UNIQUE,
    estado TEXT NOT NULL CHECK (estado IN ('disponivel','emprestado','reservado','em_reparo','baixado'))
);
CREATE TABLE IF NOT EXISTS emprestimos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exemplar_id INTEGER NOT NULL REFERENCES exemplares(id),
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    categoria TEXT NOT NULL,
    data_retirada TEXT NOT NULL,
    data_prevista TEXT NOT NULL,
    data_devolucao TEXT,
    estado TEXT NOT NULL CHECK (estado IN ('ativo','devolvido','atrasado')),
    renovacoes INTEGER NOT NULL DEFAULT 0,
    dias_atraso INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS exemplar_em_uso ON emprestimos(exemplar_id)
    WHERE data_devolucao IS NULL;
CREATE INDEX IF NOT EXISTS emprestimos_usuario ON emprestimos(usuario_id);
CREATE TABLE IF NOT EXISTS reservas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    livro_id INTEGER NOT NULL REFERENCES livros(id),
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    exemplar_id INTEGER REFERENCES exemplares(id),
    data TEXT NOT NULL,
    disponivel_ate TEXT,
    estado TEXT NOT NULL CHECK (estado IN ('aguardando','disponivel','expirada','cancelada'))
);
CREATE UNIQUE INDEX IF NOT EXISTS reserva_ativa_usuario ON reservas(livro_id, usuario_id)
    WHERE estado IN ('aguardando','disponivel');
CREATE UNIQUE INDEX IF NOT EXISTS exemplar_separado ON reservas(exemplar_id)
    WHERE estado = 'disponivel';
CREATE INDEX IF NOT EXISTS reservas_livro ON reservas(livro_id, estado, id);
CREATE TABLE IF NOT EXISTS multas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emprestimo_id INTEGER NOT NULL UNIQUE REFERENCES emprestimos(id),
    valor_centavos INTEGER NOT NULL,
    pago_centavos INTEGER NOT NULL DEFAULT 0,
    estado TEXT NOT NULL CHECK (estado IN ('aberta','paga','perdoada'))
);
