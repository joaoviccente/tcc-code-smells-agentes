# API da Biblioteca Universitária

API REST em Python 3.11+ com FastAPI e persistência em SQLite.

## Executar

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app
```

A documentação interativa fica em `http://127.0.0.1:8000/docs`. A API cria o arquivo `biblioteca.sqlite3` na primeira execução. Defina a variável de ambiente `BIBLIOTECA_DB` para usar outro arquivo.

## Endpoints

| Recurso | Método e caminho |
| --- | --- |
| Usuários | `POST /usuarios`, `GET /usuarios`, `GET /usuarios/{id}`, `PUT /usuarios/{id}`, `DELETE /usuarios/{id}` |
| Livros | `POST /livros`, `GET /livros`, `GET /livros/{id}`, `PUT /livros/{id}`, `DELETE /livros/{id}` |
| Exemplares | `POST /exemplares`, `GET /exemplares`, `GET /exemplares/{id}`, `PUT /exemplares/{id}`, `DELETE /exemplares/{id}` |
| Empréstimos | `POST /emprestimos`, `POST /emprestimos/{id}/renovar`, `POST /emprestimos/{id}/devolver`, `GET /usuarios/{id}/emprestimos` |
| Reservas | `POST /reservas`, `POST /reservas/{id}/cancelar`, `GET /livros/{id}/reservas` |
| Multas | `GET /usuarios/{id}/multas`, `POST /multas/{id}/pagar` |
| Relatórios | `GET /relatorios/livros-mais-emprestados?inicio=2026-11-01&fim=2026-11-30`, `GET /relatorios/usuarios-com-mais-atrasos`, `GET /relatorios/taxa-ocupacao-por-area` |

Criações retornam `201`, demais consultas e alterações bem-sucedidas retornam `200` e exclusões retornam `204`. A API retorna `404` para registros ausentes, `409` para conflitos de circulação, duplicidade ou vínculos que impedem exclusão, e `422` para entradas inválidas.

## Comportamento da circulação

- Os empréstimos usam datas de calendário em UTC−03:00 e as regras da categoria registrada na retirada. A renovação soma o prazo ao vencimento vigente.
- Após o 15º dia de atraso, a suspensão automática é recalculada enquanto o empréstimo está aberto. Na devolução, é fixada pela soma do dobro dos dias de atraso à data de devolução. Se houver várias suspensões, vale a data mais distante. Uma suspensão administrativa pode ser alterada pelo CRUD de usuários.
- A disponibilidade de uma reserva começa na devolução de um exemplar ou na liberação de um exemplar reservado por cancelamento ou expiração. Cada oferta vale 48 horas. O empréstimo do exemplar reservado pelo titular consome a reserva. A posição começa em 1 e é recalculada sobre as reservas vigentes.
- A multa usa centavos internamente. O pagamento quita o saldo acumulado. Se um empréstimo ainda aberto acumular mais multa depois do pagamento, o saldo adicional volta a ficar aberto.
- A aplicação atualiza atrasos, suspensões, multas e expirações na inicialização, antes das operações da API e a cada minuto enquanto estiver em execução.
- O relatório de livros usa a data de retirada e inclui as duas datas do intervalo. O relatório de atrasos conta empréstimos que passaram do prazo, inclusive os já devolvidos. A taxa de ocupação divide o total de exemplares emprestados pelo total de exemplares que integram o acervo da área, excluindo os baixados.
