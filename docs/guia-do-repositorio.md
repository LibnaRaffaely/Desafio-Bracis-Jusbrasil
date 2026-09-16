# bracis-citacoes

Verificador de citações jurídicas para o Desafio BRACIS 2026 (Jusbrasil).
Pipeline híbrido orquestrado com LangGraph: nós determinísticos
(extração, normalização, catálogo, decisão, calibração) e três agentes LLM
opcionais ligados por arestas condicionais.

## Começando

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # uv
make setup                                         # ambiente base
# copie os dados do Kaggle para data/ (ver data/README.md)
make check-data
```

`make setup-llm` instala também os agentes (compila o llama.cpp). Só é
necessário quando alguém for trabalhar neles.

Dados da competição e pesos de modelos **nunca** vão para o git.

## Estrutura

```
docs/           arquitetura, contratos, avaliação, decisões, reprodutibilidade
scripts/        check_data.py
src/citacoes/
├── grafo/      estados, montagem dos grafos, roteamento
├── nos/        nós determinísticos (funções puras)
├── agentes/    agentes LLM, schemas e prompts
├── catalogo/   construção offline do catálogo canônico
├── dominio/    léxico, chave-esqueleto, injetor de ruído
└── avaliacao/  métrica local, três modos, portão de regressão
params/         parâmetros ajustados que vão no bundle
baseline/       melhor score aceito
notebooks/      exploração livre
tests/
```

Cada pasta tem um README com o que entra nela. Comece por
`docs/arquitetura.md`.

## Como trabalhamos

- Os nomes de campos e as invariantes de `docs/contratos.md` só mudam com
  acordo dos três. O resto da implementação é livre.
- Uma branch por tarefa, PR pequeno, revisão de outra pessoa.
- Nenhum merge baixa o score de um nível nem aumenta τ
  (`docs/avaliacao.md`).
- Decisões com evidência em `docs/decisoes.md`.
- Submissões por uma pessoa só, com changelog e score local por nível.
- Agentes LLM ficam desligados até a análise de erro mostrar que valem.

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
