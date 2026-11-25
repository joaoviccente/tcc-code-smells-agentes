# API da biblioteca universitária

## Executar

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app:app
```

A documentação interativa fica em http://127.0.0.1:8000/docs. A API cria o banco
SQLite `biblioteca.db` ao receber a primeira operação. Use a variável de ambiente
`BIBLIOTECA_DB` para escolher outro caminho.

## Endpoints

| Operação | Método e caminho |
| --- | --- |
| Criar e listar usuários, livros e exemplares | `POST` e `GET` em `/usuarios`, `/livros` e `/exemplares` |
| Consultar, substituir e excluir | `GET`, `PUT` e `DELETE` em `/usuarios/{id}`, `/livros/{id}` e `/exemplares/{id}` |
| Retirar um exemplar | `POST /emprestimos` com `exemplar_id` e `usuario_id` |
| Renovar ou devolver | `POST /emprestimos/{id}/renovar` e `POST /emprestimos/{id}/devolver` |
| Listar empréstimos | `GET /usuarios/{id}/emprestimos` |
| Criar ou cancelar uma reserva | `POST /reservas` com `livro_id` e `usuario_id`, e `POST /reservas/{id}/cancelar` |
| Consultar fila | `GET /livros/{id}/reservas` |
| Listar multas e registrar pagamento | `GET /usuarios/{id}/multas` e `POST /multas/{id}/pagamento` |
| Ranking de empréstimos | `GET /relatorios/livros-mais-emprestados?inicio=2026-01-01&fim=2026-12-31` |
| Ranking de atrasos | `GET /relatorios/usuarios-com-mais-atrasos` |
| Ocupação por área | `GET /relatorios/ocupacao-por-area` |

As datas seguem UTC. A API concilia atrasos e vencimentos de reservas em cada
operação. O prazo do próximo da fila começa no instante de expiração da reserva
anterior. Exemplares livres podem atender uma reserva imediatamente. Cada retirada
atende a reserva vinculada àquele exemplar.

A renovação acrescenta o prazo da categoria à data prevista. O empréstimo conserva
a categoria registrada na retirada. A suspensão automática é recalculada enquanto
o atraso segue em curso. Na devolução, o prazo final corresponde ao dobro do atraso
contado a partir da devolução. Suspensões administrativas continuam até a alteração
do cadastro. As multas são armazenadas em centavos e o pagamento é registrado após
a devolução, quando o valor fica definitivo.

O relatório de ocupação divide os exemplares emprestados pelo acervo operacional
(disponíveis, emprestados e reservados). O ranking de atrasos conta empréstimos que
ultrapassaram a data prevista. O ranking de livros usa as datas de retirada e inclui
as duas datas informadas. Ambos os rankings aceitam `limite` de 1 a 100.

As respostas usam 201 para criações, 204 para exclusões, 403 para retirada por
usuário suspenso, 404 para registros ausentes, 409 para conflitos e 422 para
entrada inválida. As exclusões respeitam os vínculos com o histórico.
