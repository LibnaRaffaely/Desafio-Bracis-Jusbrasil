# bracis-citacoes

Verificador de citações jurídicas para o Desafio BRACIS 2026 (Jusbrasil).
Pipeline determinístico orquestrado com LangGraph: extração, normalização,
catálogo, decisão e calibração. A arquitetura previa três agentes LLM
opcionais (extrator, parser e juiz); eles continuam no código, mas ficam
desligados na solução entregue (D8 em `docs/decisoes.md`).

## Começando

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # uv
make setup                                         # ambiente base
# copie os dados do Kaggle para data/ (ver data/README.md)
make check-data
```

`make setup-llm` instala também os agentes (compila o llama.cpp). A
solução entregue não precisa dele; só serve para quem for retomar os
agentes.

Dados da competição e pesos de modelos **nunca** vão para o git.

## Estrutura

```
docs/           arquitetura, contratos, avaliação, decisões, reprodutibilidade
scripts/        checagem dos dados, ajuste da confiança, avaliação da extração e da decisão
oficiais/       scripts oficiais do desafio (json_to_submission.py, kaggle_metric.py), sem alteração
src/citacoes/
├── grafo/      estados, montagem dos grafos, roteamento
├── nos/        nós determinísticos (funções puras)
├── agentes/    agentes LLM, schemas e prompts (desligados, D8)
├── catalogo/   construção offline do catálogo canônico
├── dominio/    léxico, chave-esqueleto, injetor de ruído
└── avaliacao/  métrica local, três modos, portão de regressão
params/         parâmetros ajustados que vão no bundle
baseline/       melhor score aceito
notebooks/      exploração livre
tests/
data/           dados da competição (fora do git, ver data/README.md)
artifacts/      catálogo canônico e hash do .db de origem (gerado, fora do git)
out/            saídas de cada execução (gerado, fora do git)
```

Cada pasta tem um README com o que entra nela. Comece por
`docs/arquitetura.md`. A descrição das pastas da entrega está na seção
"Organização do repositório" do [README](../README.md).

## Como trabalhamos

- Os nomes de campos e as invariantes de `docs/contratos.md` só mudam com
  acordo dos três. O resto da implementação é livre.
- Uma branch por tarefa, PR pequeno, revisão de outra pessoa.
- Nenhum merge baixa o score de um nível nem aumenta τ
  (`docs/avaliacao.md`).
- Decisões com evidência em `docs/decisoes.md`.
- Submissões por uma pessoa só, com changelog e score local por nível.
- Agentes LLM ficam desligados até a análise de erro mostrar que valem; na
  entrega, ela não mostrou (D8).

## Datas

| Quando | O quê |
|---|---|
| 18/09 | reunião das hipóteses H1–H4 |
| 21/09 | primeira submissão com o grafo determinístico |
| 28/09 | congelamento: só bundle, revisão e submissão |
| 30/09, 23h59 | fechamento |

## Licença

Apache-2.0 (as regras só permitem compartilhar código publicamente sob
licença aberta sem restrição comercial). Adicionem o `LICENSE` ao criar o
repositório no GitHub.
