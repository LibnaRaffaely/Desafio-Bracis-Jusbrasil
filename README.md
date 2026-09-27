# Desafio-Bracis-Jusbrasil

Verificador de citações jurídicas para o Desafio BRACIS 2026 (Jusbrasil).
Pipeline híbrido orquestrado com LangGraph: nós determinísticos (extração,
normalização, catálogo, decisão) e um Agente-Juiz LLM opcional.

## Como executar

### 1. Pré-requisitos

- Python 3.12 (fixado em `.python-version`; o mínimo é 3.11).
- [uv](https://docs.astral.sh/uv/) para gerenciar o ambiente.
- `make` é opcional. Sem ele, use os comandos `uv run ...` indicados abaixo.
- Para o Agente-Juiz: GPU com CUDA e os pesos do modelo baixados localmente.

Instalação do uv:

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Instalar o ambiente

```bash
uv sync --frozen          # ambiente base (equivale a: make setup)
```

Extras opcionais:

| Comando | Quando usar |
|---|---|
| `uv sync --extra juiz` | Liga o Agente-Juiz (`transformers` + `torch`) |
| `uv sync --extra llm` | Agentes via llama.cpp (compila na instalação; equivale a `make setup-llm`) |

### 3. Colocar os dados

Os dados da competição não vão para o git. Baixe-os da aba *Data* do Kaggle
e organize assim:

```
data/
├── txt/                    # documentos de entrada (.txt)
├── desafio1_bracis.db      # base de referência (SQLite)
├── goldenset_offsets.csv   # gabarito do dev set
├── json_to_submission.py   # script oficial
├── kaggle_metric.py        # métrica oficial
└── sample_submission.csv
```

Confira se está tudo certo:

```bash
uv run python scripts/check_data.py data     # ou: make check-data
```

O script sai com código 1 se faltar arquivo ou se os offsets do gabarito não
baterem com os `.txt`.

### 4. Gerar a submissão

Na **primeira execução**, o catálogo canônico precisa ser construído a partir
da base (etapa offline). Ele fica em cache em `artifacts/` e é reaproveitado
nas execuções seguintes.

```bash
# primeira vez: constrói o catálogo e roda o pipeline
make rodar ARGS="--construir-catalogo"

# execuções seguintes
make rodar

# rodar e avaliar localmente contra o gabarito
make rodar ARGS="--avaliar"
```

A confiança de cada citação vem de `params/tabela_confianca.json`. Sem esse
arquivo, a submissão sai sem confiança e perde o bônus de calibração, que
vale até 10%. Depois de mudar a extração, a busca ou a decisão, ajuste a
tabela de novo e rode outra vez:

```bash
make rodar                       # gera out/rastro.jsonl
make calibrar                    # grava params/tabela_confianca.json
make rodar ARGS="--avaliar"
```

Sem `make`, o ajuste é `uv run python scripts/ajustar_confianca.py`.
Detalhes em [params/README.md](params/README.md).

Sem `make`, o comando da rodada é:

```bash
uv run python -m citacoes.rodar --txt data/txt --saida out --oficiais data \
    --db data/desafio1_bracis.db --gabarito data/goldenset_offsets.csv \
    --construir-catalogo --avaliar
```

Saídas geradas em `out/`:

| Arquivo | Conteúdo |
|---|---|
| `submission.csv` | Submissão no formato do Kaggle |
| `json/` | Um JSON por documento |
| `rastro.jsonl` | Uma linha por citação, com método de busca e de decisão |
| `scores.json` | Score por nível, macro-F1 e τ (só com `--avaliar`) |

Antes de terminar, o pipeline confere as invariantes de `docs/contratos.md`
e falha se alguma for quebrada. Com `--avaliar`, ele também compara o
resultado com `baseline/scores.json` e avisa se algum nível piorou.

### 5. Ligar o Agente-Juiz (opcional)

```bash
uv sync --extra juiz
uv run python -m citacoes.rodar --juiz --modelo CAMINHO_DOS_PESOS --seed 42 --avaliar
```

`--modelo` aceita um caminho local ou um id do Hugging Face. Com id do
Hugging Face, `--revisao COMMIT` é obrigatório. A execução não usa rede: os
pesos precisam já estar baixados.

### Opções da linha de comando

| Opção | Padrão | Descrição |
|---|---|---|
| `--txt` | `data/txt` | Pasta com os documentos `.txt` |
| `--saida` | `out` | Pasta de saída |
| `--oficiais` | `data` | Pasta com os scripts oficiais do Kaggle |
| `--db` | `data/desafio1_bracis.db` | Base usada para construir o catálogo |
| `--artifacts` | `artifacts` | Onde o catálogo construído fica salvo |
| `--params` | `params` | Pasta da tabela de confiança |
| `--construir-catalogo` | desligado | Reconstrói o catálogo a partir da base |
| `--avaliar` | desligado | Calcula a métrica local com o gabarito |
| `--gabarito` | `data/goldenset_offsets.csv` | Gabarito usado em `--avaliar` |
| `--baseline` | `baseline/scores.json` | Score de referência para o portão de regressão |
| `--juiz` | desligado | Liga o Agente-Juiz |
| `--modelo` / `--revisao` | — | Pesos do juiz e commit fixado |
| `--seed` | `42` | Seed do juiz |

Ajuda completa: `uv run python -m citacoes.rodar --help`.

### Testes e qualidade de código

```bash
uv run pytest                                   # make test
uv run ruff check src tests scripts             # make lint
uv run ruff format src tests scripts            # make format
uv run python -m citacoes.grafo.montagem        # make grafo: exporta docs/grafo.mmd
```

Avaliação isolada do nó de decisão (Módulo 4):

```bash
uv run python scripts/avalia_decisao.py --dados data --modo isolado
uv run python scripts/avalia_decisao.py --dados data --modo integrado
```

## Documentação

Comece por [docs/arquitetura.md](docs/arquitetura.md). Os demais documentos
estão em [docs/](docs/): contratos, avaliação, decisões e reprodutibilidade.
