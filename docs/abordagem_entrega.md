# Abordagem da entrega

# Rascunho
## Visão geral
Resumo em poucas linhas do problema e da solução.

## Pipeline
Etapas em ordem: extração, normalização, busca no catálogo, decisão, confiança.
(Indicar o diagrama em docs/grafo.mmd, se quiser.)

## Catálogo canônico
Como é construído a partir do .db (enriquecimento, índices FTS5) e quando é reconstruído.

## Decisão e calibração
Heurística usada e como a tabela de confiança é gerada (params/tabela_confianca.json).

## Reprodutibilidade
Execução offline, sem modelos, versões fixadas (Docker, uv.lock), determinismo da saída.

## Resultados
Score local por nível (out/scores.json) e comparação com o baseline.

## Limitações e próximos passos