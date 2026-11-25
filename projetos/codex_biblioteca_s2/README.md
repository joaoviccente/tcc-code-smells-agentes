# API da biblioteca universitária

A API usa FastAPI e SQLite. O banco é criado na inicialização no arquivo
`biblioteca.db`. A variável de ambiente `BIBLIOTECA_DB` define outro caminho.

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app:app
```

A documentação interativa fica em <http://127.0.0.1:8000/docs>.

| Recurso | Operações |
| --- | --- |
| Usuários, livros e exemplares | `GET` e `POST` nas coleções `/usuarios`, `/livros` e `/exemplares`. `GET`, `PUT` e `DELETE` no item `/{id}`. |
| Empréstimos | `POST /emprestimos` com `usuario_id` e `exemplar_id`. `POST /emprestimos/{id}/renovar`, `POST /emprestimos/{id}/devolver` e `GET /usuarios/{id}/emprestimos`. |
| Reservas | `POST /reservas` com `livro_id` e `usuario_id`. `POST /reservas/{id}/cancelar` e `GET /livros/{id}/reservas`. |
| Multas | `GET /usuarios/{id}/multas` e `POST /multas/{id}/pagar`. |
| Relatórios | `GET /relatorios/livros-mais-emprestados?inicio=AAAA-MM-DD&fim=AAAA-MM-DD`, `GET /relatorios/usuarios-com-mais-atrasos` e `GET /relatorios/ocupacao-por-area`. |

A API usa datas corridas em UTC para prazos e multas e horas corridas para
reservas. As transições dependentes do relógio são aplicadas na próxima
operação da API, usando os horários originais de vencimento para avançar
a fila. Um exemplar livre pode ser separado imediatamente para a primeira
reserva. A retirada usa o endpoint de criação de empréstimo. A renovação
estende a data prevista pelo prazo da categoria registrada na retirada.

A suspensão automática começa no 16º dia de atraso. Na devolução,
o prazo total do bloqueio é fixado em duas vezes o atraso final,
contado a partir do início da suspensão. Multas são armazenadas em
centavos. Se houver pagamento antes da devolução e a multa aumentar,
apenas a diferença volta a ficar em aberto.

O período do relatório de empréstimos inclui ambas as datas. A ocupação
é a fração de exemplares emprestados entre os exemplares que compõem o
acervo de cada área, excluindo os baixados. Exclusões que comprometeriam
vínculos ou o histórico retornam HTTP 409.
