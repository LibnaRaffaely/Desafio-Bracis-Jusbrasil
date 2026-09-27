# params/

Parâmetros ajustados no dev set que vão no bundle. Versionados no git.
Nada aqui é reajustado no conjunto final, que é cego.

## tabela_confianca.json

Confiança por citação, lida pelo nó `calibrar` (`src/citacoes/nos/calibrar.py`).
Sem este arquivo, a confiança sai `-` no CSV e o bônus de calibração da
métrica fica zero.

A métrica soma até 10% ao score de cada nível:
`score = s × (1 + 0,1 × (1 − Brier))`. O Brier só olha as citações casadas
com o gabarito. O valor que minimiza o Brier num grupo de citações é a taxa
de acerto do grupo, e é isso que a tabela guarda.

Formato:

```json
{
  "versao": 1,
  "chave": "metodo_decisao|metodo_busca",
  "priori": {"alfa": 1.0, "beta": 1.0},
  "faixas": {
    "cardinalidade_1|catalogo": {"confianca": 0.9815, "acertos": 52, "total": 52}
  },
  "por_metodo_decisao": {
    "cardinalidade_1": {"confianca": 0.9859, "acertos": 69, "total": 69}
  },
  "padrao": 0.8883
}
```

Busca da confiança: primeiro a faixa `metodo_decisao|metodo_busca`, depois
só `metodo_decisao`, depois `padrao`. A taxa é suavizada por Laplace,
`(acertos + alfa) / (total + alfa + beta)`, para que faixas pequenas não
virem 0 ou 1 exatos.

Como gerar:

```bash
make rodar        # gera out/rastro.jsonl
make calibrar     # grava params/tabela_confianca.json
make rodar ARGS="--avaliar"
```

**Refaça o ajuste sempre que a extração, a busca ou a decisão mudarem.** A
tabela mede o pipeline que gerou o rastro. Com um pipeline diferente, ela
fica descalibrada. O script mostra também o Brier deixando um documento de
fora, que é a estimativa honesta para o conjunto cego.
