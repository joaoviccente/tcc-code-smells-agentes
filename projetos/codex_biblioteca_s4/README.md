# Biblioteca Universitária

API REST em Python com FastAPI e SQLite. Use Python 3.11 ou superior.

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app
```

Abra http://127.0.0.1:8000/docs para consultar os campos e executar requisições. O banco é criado automaticamente em `biblioteca.db`. A variável de ambiente `BIBLIOTECA_DB` permite informar outro caminho.

| Operação | Método e caminho |
| --- | --- |
| Criar e listar cadastros | `POST` e `GET` em `/usuarios`, `/livros` e `/exemplares` |
| Consultar, substituir e excluir cadastro | `GET`, `PUT` e `DELETE` em `/{colecao}/{id}` |
| Emprestar exemplar | `POST /emprestimos` com `usuario_id` e `exemplar_id` |
| Renovar ou devolver | `POST /emprestimos/{id}/renovar` e `POST /emprestimos/{id}/devolver` |
| Consultar empréstimos | `GET /usuarios/{id}/emprestimos` |
| Reservar livro | `POST /reservas` com `usuario_id` e `livro_id` |
| Cancelar reserva | `POST /reservas/{id}/cancelar` |
| Consultar fila | `GET /livros/{id}/reservas` |
| Consultar multas | `GET /usuarios/{id}/multas` |
| Registrar pagamento do saldo | `POST /multas/{id}/pagar` |
| Ranking de livros por retirada | `GET /relatorios/livros-mais-emprestados?inicio=2026-01-01&fim=2026-12-31` |
| Ranking por quantidade de empréstimos com atraso | `GET /relatorios/usuarios-com-mais-atrasos` |
| Ocupação atual por área | `GET /relatorios/ocupacao-por-area` |

O período do ranking é inclusivo. A taxa de ocupação é a porcentagem de exemplares emprestados ou reservados sobre o total de exemplares que ainda constam no acervo, incluindo os que estão em reparo.

Os vencimentos usam dias corridos e o horário UTC−03:00. A renovação acrescenta o prazo da categoria ao vencimento vigente. A categoria registrada na retirada rege as renovações e multas daquele empréstimo. A suspensão automática é recalculada enquanto o empréstimo estiver em atraso e termina após o dobro do atraso apurado na devolução. O pagamento quita o saldo acumulado e novos dias de atraso podem gerar saldo adicional até o teto.

Um exemplar livre fica separado imediatamente para a primeira reserva elegível da fila. A retirada consome a reserva. A API atualiza atrasos, suspensões e expirações a cada requisição ao banco, usando o horário original de expiração para iniciar o prazo da pessoa seguinte na fila.

Para executar os testes de integração, instale `pytest` e `httpx2` e execute `python -m pytest -q`.
