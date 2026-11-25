# Biblioteca Universitária

API REST em FastAPI com SQLite. O banco é criado na inicialização. Defina
`BIBLIOTECA_DB` para usar outro caminho além de `biblioteca.db`.

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app
```

Acesse [Swagger UI](http://127.0.0.1:8000/docs) para consultar os esquemas
e executar operações.

| Operação | Rota |
| --- | --- |
| Criar ou listar usuários, livros e exemplares | `POST` ou `GET` em `/usuarios`, `/livros` e `/exemplares` |
| Consultar, substituir ou excluir um registro | `GET`, `PUT` ou `DELETE` em cada coleção com `/{id}` |
| Abrir ou listar empréstimos | `POST /emprestimos` ou `GET /emprestimos?usuario_id=1` |
| Renovar ou devolver | `POST /emprestimos/{id}/renovar` ou `POST /emprestimos/{id}/devolver` |
| Criar, cancelar ou listar reservas na fila | `POST /reservas`, `POST /reservas/{id}/cancelar`, `GET /livros/{id}/reservas` |
| Listar multas ou registrar pagamento integral do saldo | `GET /multas?usuario_id=1` ou `POST /multas/{id}/pagar` |
| Empréstimos por livro em um período inclusivo | `GET /relatorios/livros-mais-emprestados?inicio=2026-01-01&fim=2026-12-31` |
| Classificação por número de empréstimos em atraso | `GET /relatorios/usuarios-com-mais-atrasos` |
| Percentual de exemplares emprestados no acervo sem baixas, por área | `GET /relatorios/ocupacao-por-area` |

Os prazos de empréstimo usam a data local do servidor. As retiradas de reservas
têm janela de 48 horas contada em UTC. Se já houver um exemplar livre, a fila
é atendida imediatamente. A retirada encerra a reserva com estado `atendida`.
Uma renovação soma o prazo da categoria ao vencimento anterior. A categoria
registrada na abertura vale durante todo o empréstimo.

Enquanto houver atraso superior a 15 dias, a data de liberação automática
acompanha o atraso corrente. Na devolução, fica fixada em duas vezes o atraso
contado a partir da data de devolução. A suspensão manual é controlada pelo
campo `situacao` do cadastro.

As multas são calculadas em centavos e apresentadas em reais. Se o saldo
for pago enquanto o empréstimo ainda está atrasado, apenas os novos encargos
voltam a ficar em aberto. A sincronização roda a cada operação e uma vez por
minuto enquanto o servidor está em execução.
