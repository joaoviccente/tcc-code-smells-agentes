# API REST – Biblioteca Universitária

FastAPI + SQLAlchemy 2 + Pydantic 2. Banco relacional SQLite por padrão
(qualquer banco suportado pelo SQLAlchemy via `BIBLIOTECA_DB_URL`, ex.:
`postgresql+psycopg://user:senha@host/biblioteca`).

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload          # documentação interativa em http://localhost:8000/docs
python -m pytest -q                    # 50 testes cobrindo todas as regras
```

## Estrutura

| Arquivo | Conteúdo |
|---|---|
| `app/regras.py` | Parâmetros por categoria e constantes das regras (valores exatos do enunciado) |
| `app/servicos.py` | Toda a lógica de negócio (regras 1–7) |
| `app/models.py` | Tabelas, com `CHECK` constraints para enums e valores |
| `app/schemas.py` | Validação de entrada (e-mail, ISBN-10/13 com dígito verificador, ano, enums, campos extras proibidos) |
| `app/routers/` | Endpoints |
| `app/clock.py` | Relógio injetável (os testes simulam a passagem de dias/horas) |

## Endpoints

| Recurso | Rotas |
|---|---|
| Usuários | `POST/GET /usuarios`, `GET/PUT/PATCH/DELETE /usuarios/{id}` |
| Livros | `POST/GET /livros`, `GET/PUT/PATCH/DELETE /livros/{id}`, `GET /livros/{id}/exemplares` |
| Exemplares | `POST/GET /exemplares`, `GET/PATCH/DELETE /exemplares/{id}` |
| Empréstimos | `POST /emprestimos`, `POST /emprestimos/{id}/renovacao`, `POST /emprestimos/{id}/devolucao`, `GET /emprestimos/{id}`, `GET /usuarios/{id}/emprestimos` (ou `GET /emprestimos?usuario_id=`) |
| Reservas | `POST /reservas`, `POST /reservas/{id}/cancelamento`, `GET /reservas/{id}`, `GET /livros/{id}/reservas` (fila) |
| Multas | `GET /usuarios/{id}/multas` (ou `GET /multas?usuario_id=`), `POST /multas/{id}/pagamento` |
| Relatórios | `GET /relatorios/livros-mais-emprestados?inicio=&fim=`, `GET /relatorios/usuarios-mais-atrasos`, `GET /relatorios/ocupacao-acervo` |

### Códigos HTTP

- `201` criação · `200` leitura/ação · `204` remoção
- `404` recurso inexistente
- `422` entrada inválida (formato, enum, ISBN, período invertido, valor de pagamento divergente)
- `409` violação de regra de negócio ou de unicidade. O corpo traz um código legível por máquina:
  `{"detail": {"codigo": "LIMITE_EXEMPLARES", "mensagem": "..."}}`

## Decisões de interpretação

- **Processamento temporal.** No início de cada requisição são aplicadas as regras que dependem do tempo:
  empréstimos vencidos viram `atrasado`, a multa acumula, a suspensão automática é aplicada/encerrada
  e reservas com mais de 48 h expiram. Não há agendador externo.
- **Atraso** = dias corridos entre a data prevista e a devolução (ou hoje). Devolver no dia previsto não gera atraso.
- **Multa (regra 5)** é criada assim que o empréstimo atrasa e cresce diariamente até o teto. Só pode ser
  paga após a devolução (antes disso o valor ainda não é definitivo); não há pagamento parcial.
  Como a multa fica `aberta` enquanto o atraso corre, ela já bloqueia novos empréstimos (regra 1).
  O perdão do professor (atraso ≤ 2 dias) é aplicado na devolução; a multa fica registrada como `perdoada`.
- **Suspensão (regra 2).** Atraso > 15 dias suspende o usuário imediatamente, mesmo antes da devolução.
  A duração (2 × dias de atraso) é contada a partir da devolução; com vários atrasos prevalece a data
  mais distante. A reativação é automática. Suspensão manual (via `PATCH situacao`) não expira sozinha.
- **Renovação** define a nova data prevista como hoje + prazo da categoria.
- **Reservas (regra 4).** Só é possível reservar quando não há exemplar `disponivel` (do contrário, basta
  emprestar). Quando um exemplar volta (devolução, saída do reparo, novo exemplar), o primeiro da fila
  passa a `disponivel` e o exemplar fica `reservado` só para ele por 48 h. Ao expirar, o prazo do próximo
  conta a partir do momento da expiração. Foi acrescentado o estado terminal **`atendida`** (reserva que
  virou empréstimo), pois nenhum dos quatro estados do enunciado representa esse desfecho.
- **Regra 6.** "Último exemplar disponível" = último exemplar ainda em circulação (`disponivel`,
  `emprestado` ou `reservado`). Se, após uma baixa, nenhum restar, todas as reservas do livro são canceladas.
  Livro sem exemplar em circulação não aceita reservas. Exemplares `baixado` não voltam a circular.
- **Regra 7.** Atraso > 60 dias na devolução: exemplar `baixado` e multa igual ao teto da categoria
  (sem perdão), com a regra 6 aplicada em seguida.
- **Estados `emprestado` e `reservado`** são controlados apenas pelo sistema; via API só é possível
  definir `disponivel`, `em_reparo` ou `baixado`.
- **Remoção** de usuário/livro/exemplar com histórico é negada (`409`) para preservar a integridade;
  para exemplares, use a baixa.
- **Relatórios.** "Mais emprestados" conta empréstimos retirados no período (datas inclusivas).
  "Mais atrasos" conta empréstimos devolvidos com atraso ou atualmente atrasados (filtro de período opcional).
  "Taxa de ocupação" = emprestados ÷ exemplares não baixados, por área.
