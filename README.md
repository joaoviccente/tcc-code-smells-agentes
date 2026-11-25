# Code smells em código gerado por agentes de codificação

Este repositório reúne os dados do Trabalho de Conclusão de Curso **"Análise comparativa de code smells em código gerado por agentes de codificação baseados em LLMs"**, de João Vicente Brasil Alves, apresentado ao curso de Sistemas de Informação da Universidade Federal do Ceará (UFC), Campus Quixadá, em 2026, sob orientação do Prof. Dr. Emanuel Ferreira Coutinho.

O estudo comparou os code smells presentes no código Python gerado por três agentes de codificação. Cada agente recebeu os mesmos três desafios de implementação de APIs REST e gerou cinco soluções independentes para cada um, totalizando 45 projetos. Os projetos foram analisados com três ferramentas de detecção de code smells voltadas a Python.

## Conteúdo

| Pasta | O que contém |
|---|---|
| `desafios/` | Os três prompts enviados aos agentes (biblioteca universitária, sistema bancário e matrícula acadêmica). |
| `projetos/` | Os 45 projetos gerados, um por pasta. |
| `resultados/` | As saídas das ferramentas de detecção para cada projeto e as planilhas com os totais usados no trabalho. |

### Nomes das pastas dos projetos

Cada pasta segue o formato `agente_desafio_sN`, em que `N` é o número da execução (de 1 a 5). Por exemplo, `claude_banco_s3` é a terceira solução do Claude Code para o desafio do sistema bancário.

## Agentes avaliados

| Agente | Versão | Modelo | Nível de raciocínio |
|---|---|---|---|
| Claude Code | 2.1.318 | Claude Opus 5.5 | medium |
| Codex CLI | 0.167.2 | GPT-6.2-Sol | low |
| Antigravity CLI | 1.5.1 | Gemini 3.8 Flash | high |

Cada projeto foi gerado a partir de um único prompt, sem intervenção durante a geração.

## Resultados

- `resultados/dpy/`, `resultados/pyexamine/` e `resultados/pysmell/` trazem as ocorrências apontadas por cada ferramenta (DPy, PyExamine e PySmell), um arquivo ou pasta por projeto. Todas as ferramentas foram usadas com seus limiares padrão, e o PySmell com a estratégia estatística.
- `resultados/metricas_por_projeto.csv` traz, para cada projeto, o tamanho (`sloc`), a complexidade ciclomática (`cc_total`), a quantidade de smells por ferramenta, as densidades por mil linhas (`*_kloc`) e por 100 pontos de complexidade (`*_cc`), o consumo de tokens e a duração da geração. A coluna `custo_usd` é o custo informado pelo próprio Claude Code, já que os outros agentes não informam esse valor.
- `resultados/custo_estimado.csv` traz o custo de cada projeto calculado pelos preços de tabela dos modelos. É o custo usado no trabalho para o Codex e o Antigravity. No Claude Code, o trabalho usa o valor informado pelo próprio agente, que coincide com o calculado, a menos de arredondamento.
- A complexidade ciclomática (`cc_total`, `funcoes` e `cc_max`) foi calculada com o Radon 6.0.1, somando todas as funções e métodos, inclusive os definidos dentro de outras funções.
- `resultados/smells_por_tipo.csv` traz o total de cada tipo de smell por ferramenta e por agente.

## Observações

- O código está como os agentes entregaram. Foram retirados apenas arquivos criados ao executar os projetos (`__pycache__`, `.pytest_cache` e bancos SQLite), os registros das sessões dos agentes e um repositório git criado por um dos agentes dentro do próprio projeto.
- Na análise, os arquivos de teste gerados pelos agentes foram desconsiderados, por isso os caminhos nos resultados se referem somente ao código da aplicação.
- Parte dos arquivos gerados pelo Codex começa com um marcador de codificação (BOM) que impedia a leitura pelas ferramentas. Esse marcador foi removido nas cópias analisadas, sem nenhuma outra alteração no código. Os arquivos deste repositório mantêm o marcador, como foram gerados.
