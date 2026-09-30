# Abordagem da entrega

Este documento descreve a solução entregue para o Desafio BRACIS 2026 (JusBrasil). Para executar, veja o [README](../README.md). Para a arquitetura completa, veja [arquitetura.md](arquitetura.md).

## Visão geral

A solução verifica citações jurídicas em documentos de texto e classifica cada uma como `real`, `inventada` ou `incompleta`. Quando a citação é real, devolve também o identificador canônico do registro na base.

A entrega é um pipeline **determinístico**: extração por regras, normalização, busca em um catálogo canônico e decisão por cardinalidade de candidatos. Não há modelo de linguagem na execução, portanto:

* não há pesos de modelos para baixar;
* a execução é totalmente offline (`--network none` no Docker);
* a mesma entrada gera sempre a mesma saída.

## Como chegamos a essa abordagem

A arquitetura foi desenhada para permitir três agentes LLM opcionais (extrator, parser e juiz), ligados por arestas condicionais do LangGraph. Na análise de erro do dev set, o pipeline determinístico resolveu todos os casos, e nenhuma citação chegou empatada ao juiz. Sem evidência de ganho, os agentes foram mantidos desligados, evitando risco de reprodutibilidade e custo de inferência. O registro da decisão está em [decisoes.md](decisoes.md) (D8).

Os agentes continuam no código, desligados por padrão, e os parâmetros que os ativam estão comentados em `src/citacoes/rodar.py`.

## Pipeline

O processamento tem duas etapas.

**1. Offline, uma vez por base:** construção do catálogo canônico a partir do `.db`. O resultado fica em `artifacts/catalogo_canonico.json`.

**2. Por documento:** um grafo extrai as citações e dispara um subgrafo independente para cada uma.

| Etapa | O que faz |
|---|---|
| `ler_documento` | Lê o texto exato, sem normalizar |
| `extrair_spans` | Encontra os trechos candidatos por regex e heurísticas |
| `normalizar` | Extrai campos estruturados (classe, tribunal, número, ano, diploma) e gera uma chave de busca |
| `buscar_no_catalogo` | Procura candidatos por consulta exata na chave |
| `decidir` | Define a classe e o identificador |
| `calibrar` | Atribui a confiança a partir de uma tabela |
| `reunir_e_formatar` | Gera o JSON do documento, depois o `submission.csv` |

O diagrama do grafo está em [arquitetura.md](arquitetura.md).

## Catálogo canônico

O catálogo é construído a partir do `.db` original, com enriquecimento permitido pelo desafio. A construção é feita pelo código em `src/citacoes/catalogo/construir.py`, a partir de qualquer `.db` no formato original.

Pontos principais:

* a busca usa uma chave normalizada, construída pelos dois lados (citação e catálogo) com a mesma função, e não uma consulta FTS5 por frase (decisão D1);
* o número próprio de cada acórdão é extraído por regras específicas por tribunal (decisão D3);
* artigos de lei só casam quando o diploma é reconhecido e igual dos dois lados (decisão D5).

Tempo de construção: [PLACEHOLDER: tempo em minutos].

## Decisão

A classe é definida pelo número de candidatos compatíveis encontrados no catálogo.

| Situação | Classe |
|---|---|
| Sem identificador no trecho | incompleta |
| Candidatos existem, mas todos têm conflito duro | inventada |
| Nenhum candidato compatível | inventada |
| Um candidato compatível | real |
| Dois ou mais compatíveis | incompleta, salvo desempate determinístico (D6) |

Na dúvida entre real e inventada, `incompleta` é a pior aposta pela métrica, por isso o desempate por cadeia de classes (D6) resolve casos como "AgInt no REsp" versus "AgInt nos EREsp".

## Calibração da confiança

A confiança de cada citação vem de `params/tabela_confianca.json`, que guarda a taxa de acerto por `metodo_decisao` e `metodo_busca`, suavizada por Laplace. A confiança nunca altera a classe nem o identificador. Sem a tabela, a submissão sai sem confiança e perde o bônus de calibração.

A tabela é gerada por `make calibrar` (ver seção 4 do README).

## Reprodutibilidade

* Execução via Docker, com Python 3.12, uv 0.5.0 e dependências fixadas em `uv.lock`.
* Sem rede durante a execução.
* Limites de recursos do desafio: até 8 CPUs e 32 GB de memória nos scripts `run`.
* Sem modelos de linguagem, sem GPU.
* Sem caminhos absolutos: os dados entram por `--db` e `--txt`, ou pela pasta `data/`.
* Determinismo da saída: [PLACEHOLDER: confirmar comparando o hash do `submission.csv` em duas execuções].

## Resultados

Medidos no dev set local (26 documentos, `goldenset_offsets.csv`), com a métrica oficial.

| | Score final | Nível 1 | Nível 2 |
|---|---|---|---|
| Código do git, dados anteriores | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] |
| **Solução entregue** | **1,0998** | [PLACEHOLDER] | [PLACEHOLDER] |

O teto da métrica é 1,1. Na solução entregue: macro-F1 [PLACEHOLDER], τ [PLACEHOLDER], bônus de calibração [PLACEHOLDER].

Score na submissão oficial do Kaggle: [PLACEHOLDER].

Evolução detalhada, com a evidência de cada mudança, em [melhorias_score.md](melhorias_score.md).

### Robustez

Com ruído sintético aplicado aos trechos do gabarito ([PLACEHOLDER: número de sementes]):

| Medida | Resultado |
|---|---|
| Inventadas marcadas como reais (τ) | [PLACEHOLDER] |
| Reais perdidas | [PLACEHOLDER] de [PLACEHOLDER] |

## Limitações

[PLACEHOLDER: a definir]

## Próximos passos

[PLACEHOLDER: a definir]