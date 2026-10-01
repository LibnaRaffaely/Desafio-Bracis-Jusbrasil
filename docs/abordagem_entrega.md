# Abordagem da entrega

Este documento resume a solução entregue para o Desafio BRACIS 2026 (JusBrasil) e as principais decisões por trás dela. Para executar, veja o [README](../README.md). Para a arquitetura completa, veja [arquitetura.md](arquitetura.md). O registro de cada decisão, com evidência, está em [decisoes.md](decisoes.md) (D1 a D10).

## Visão geral

A solução verifica citações jurídicas em documentos de texto e classifica cada uma como `real`, `inventada` ou `incompleta`. Quando a citação é real, devolve também o identificador canônico do registro na base.

A entrega é um pipeline **determinístico**: extração por regras, normalização, busca em um catálogo canônico e decisão por cardinalidade de candidatos. Não há modelo de linguagem na execução.

## Como chegamos a essa abordagem

A arquitetura foi desenhada para permitir três agentes LLM opcionais (extrator, parser e juiz), ligados por arestas condicionais do LangGraph. Na análise de erro do dev set, o pipeline determinístico resolveu todos os casos, e nenhuma citação chegou empatada ao juiz. Sem evidência de ganho, os agentes foram mantidos desligados, evitando risco de reprodutibilidade e custo de inferência (D8).

Os agentes continuam no código, desligados por padrão, e os parâmetros que os ativam estão comentados em `src/citacoes/rodar.py`.

## Pipeline

O processamento tem duas etapas.

**1. Uma vez por base:** construção do catálogo canônico a partir do `.db`. O resultado fica em `artifacts/catalogo_canonico.json`.

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

O catálogo é construído a partir do `.db` original, com enriquecimento permitido pelo desafio, pelo código em `src/citacoes/catalogo/construir.py`. Funciona com qualquer `.db` no formato original.

Pontos principais:

* a busca usa uma chave normalizada, construída pelos dois lados (citação e catálogo) com a mesma função, e não uma consulta FTS5 por frase (D1);
* o número próprio de cada acórdão é extraído por regras específicas por tribunal (D3);
* artigos de lei só casam quando o diploma é reconhecido e igual dos dois lados (D5);
* o hash SHA-256 do `.db` de origem fica em `artifacts/catalogo_canonico.db.sha256`. Se a base mudar, o pipeline para e pede `--construir-catalogo`, em vez de reaproveitar em silêncio um catálogo de outra base (D10).

Tempo de construção: cerca de 20 s para a base do desafio (90 MB), medido no Docker com o limite de 8 CPUs. Uma execução completa com `--avaliar` levou 39 s com a construção do catálogo e 20 s com o catálogo pronto, sem contar o build da imagem (cerca de 45 s na primeira vez).

## Decisão

A classe é definida pelo número de candidatos compatíveis (sem conflito duro) encontrados no catálogo, nesta ordem:

| Situação | Classe |
|---|---|
| Sem identificador buscável no trecho | incompleta |
| Candidatos existem, mas todos têm conflito duro | inventada |
| Nenhum candidato compatível | inventada |
| Um candidato compatível | real |
| Dois ou mais compatíveis | real, se um desempate determinístico resolver; senão incompleta |

Os desempates são dois: registros com o mesmo conteúdo colapsam em um só, e, se apenas um registro tem exatamente a cadeia de classes citada, ele vence (D6). É o que separa "AgInt no REsp" de "AgInt nos EREsp" com o mesmo número. Vale desempatar porque `incompleta` erra tanto se a citação for real quanto se for inventada.

## Calibração da confiança

A confiança de cada citação vem de `params/tabela_confianca.json`, que guarda a taxa de acerto por `metodo_decisao` e `metodo_busca` no dev set, suavizada por Laplace (α = β = 1). Essa taxa é o valor que minimiza o Brier da métrica (D2). A confiança nunca altera a classe nem o identificador. Sem a tabela, a submissão sai sem confiança e perde o bônus de calibração.

A tabela é gerada por `make calibrar` (seção 4 do README), fica versionada em `params/` e a imagem Docker a copia no build.

## Reprodutibilidade

* Execução via Docker, com Python 3.12, uv 0.5.0 e dependências fixadas em `uv.lock`.
* Rede só para construir a imagem na primeira vez; a execução roda sem rede (`--network none`).
* Limites de recursos do desafio: até 8 CPUs e 32 GB de memória nos scripts `run`.
* Sem modelos de linguagem, sem GPU.
* Sem caminhos absolutos: os dados entram por `--db` e `--txt`, ou pela pasta `data/`.
* O container é removido ao fim de cada execução (`--rm`, D9); os resultados ficam em `out/` e `artifacts/`.

## Resultados

Medidos no dev set local (26 documentos, 192 citações, `goldenset_offsets.csv`), com a métrica oficial (`oficiais/kaggle_metric.py`).

| | Score final | Nível 1 | Nível 2 |
|---|---|---|---|
| Ponto de partida (código anterior, mesmos dados) | 0,8307 | 0,8789 | 0,8066 |
| **Solução entregue** | **1,0998** | **1,0999** | **1,0998** |

O teto da métrica é 1,1. Na solução entregue, nos dois níveis: macro-F1 1,0, τ = 0 e bônus de calibração 0,0999 (nível 1) e 0,0998 (nível 2). O resultado foi reproduzido num clone limpo da branch de entrega seguindo a seção 3 do README.

Evolução detalhada, com a evidência de cada mudança, em [melhorias-score.md](melhorias-score.md).
a
## Limitações

* O score do dev set é otimista: as regras foram desenhadas olhando para ele, e o conjunto final é cego. Dois indícios de que a solução não apenas decora o dev set: o bônus de calibração medido deixando um documento de fora fica em 0,093, contra 0,094 no próprio dev set, e, com ruído sintético em 10 sementes, as inventadas marcadas como reais (τ) caíram de 11 para 0 ([melhorias-score.md](melhorias-score.md)).
* Formas de citação ausentes do dev set não estão cobertas.
* O relatório `erros.csv` (uma linha por citação com a categoria do erro, previsto em [avaliacao.md](avaliacao.md)) não é gerado nesta versão. Para o módulo de decisão, `scripts/avalia_decisao.py` já gera um CSV equivalente, usando os spans do gabarito.
* Os agentes LLM não foram validados, pois nenhuma citação do dev set chegou a eles.

