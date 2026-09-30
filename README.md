# Desafio BRACIS – JusBrasil

Verificador de citações jurídicas para o Desafio BRACIS 2026 (JusBrasil).
Pipeline híbrido orquestrado com LangGraph: nós determinísticos de extração,
normalização, busca em catálogo canônico (SQLite FTS5) e decisão por
heurística calibrada.

## Como executar

### 1. Pré-requisitos

**Para reprodução e avaliação:**
- [Docker](https://docs.docker.com/get-docker/)

**Para desenvolvimento:**
- Python 3.12 (fixado em `.python-version`; mínimo 3.11)
- [uv](https://docs.astral.sh/uv/) para gerenciar o ambiente
- `make` é opcional; sem ele, use os comandos `uv run ...` indicados abaixo

Instalação do uv:

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Dados

Os dados da competição não vão para o git. Baixe-os da aba *Data* do Kaggle.
Você precisará de dois itens:

- O arquivo `.db` (base SQLite de referência)
- Uma pasta com os documentos `.txt` de entrada

### 3. Reprodução e avaliação

Clone o repositório e entre na pasta:

```bash
git clone https://github.com/LibnaRaffaely/Desafio-Bracis-Jusbrasil
cd Desafio-Bracis-Jusbrasil
```

Os scripts `run.sh` (Linux/macOS) e `run.ps1` (Windows) constroem a imagem
Docker na primeira execução, detectam se o catálogo precisa ser reconstruído
(quando `artifacts/catalogo_canonico.json` não existe) e gravam a saída em
`out/submission.csv`.

```bash
# Linux/macOS

# usa os dados de data/
bash run.sh

# informa o banco e a pasta de documentos
bash run.sh --db <caminho_db> --txt <pasta_txt>

# gera a submissão e calcula o score local (usa data/goldenset_offsets.csv)
bash run.sh --avaliar

# usa outro gabarito, em qualquer pasta
bash run.sh --avaliar --gabarito <caminho_gabarito>
```

```powershell
# Windows PowerShell

# usa os dados de data/
.\run.ps1

# informa o banco e a pasta de documentos
.\run.ps1 --db <caminho_db> --txt <pasta_txt>

# gera a submissão e calcula o score local (usa data/goldenset_offsets.csv)
.\run.ps1 --avaliar

# usa outro gabarito, em qualquer pasta
.\run.ps1 --avaliar --gabarito <caminho_gabarito>
```

No PowerShell, `-Banco` e `-Txts` continuam aceitos como equivalentes a
`--db` e `--txt`.

Todos os argumentos são opcionais e podem ser passados em qualquer ordem.
Sem `--db` e `--txt`, os scripts usam os dados da pasta `data/`
(conforme o `data/README.md`).

Todos os parâmetros estão na [tabela de parâmetros](#6-parâmetros). 
A coluna "Scripts Docker" indica quais funcionam nos scripts `run.sh` e `run.ps1`.


> **NOTA**:
> A imagem Docker só é construída se ainda não existir. Use `--rebuild` para
> reconstruí-la depois de alterar `src/`, `scripts/`, `oficiais/`, `baseline/`,
> `params/` (por exemplo, ao recalibrar a confiança) ou as dependências
> (`pyproject.toml` e `uv.lock`).
>
> O catálogo é outro caso: se a base `.db` mudar, apague
> `artifacts/catalogo_canonico.json` para que a próxima execução o reconstrua.
> `--rebuild` não mexe no catálogo.

### 4. Desenvolvimento

> **NOTA**:
> O Makefile sempre usa a pasta `data/`. Preencha-a conforme o `data/README.md` antes de rodar qualquer comando.

**Instalar o ambiente:**

```bash
uv sync --frozen
```

**Rodar o pipeline:**

```bash
# primeira execução: constrói o catálogo canônico
make rodar ARGS="--construir-catalogo"

# execuções seguintes
make rodar

# rodar e avaliar localmente contra o gabarito
make rodar ARGS="--avaliar"
```

Sem `make`:

```bash
uv run python -m citacoes.rodar \
    --db <caminho_db> \
    --txt <pasta_txt> \
    --saida out \
    --construir-catalogo \
    --avaliar
```

**Calibrar a confiança**:

A confiança de cada citação vem de `params/tabela_confianca.json`. Sem esse
arquivo, a submissão sai sem confiança e perde o bônus de calibração, que
vale até 10%. Depois de mudar a extração, a busca ou a decisão, ajuste a
tabela de novo e rode outra vez:

```bash
make rodar                     # gera out/rastro.jsonl
make calibrar                  # grava params/tabela_confianca.json
make rodar ARGS="--avaliar"
```

Sem `make`: `uv run python scripts/ajustar_confianca.py`.
Detalhes em [params/README.md](params/README.md).

### 5. Saídas geradas em `out/`:

| Arquivo | Conteúdo |
|---|---|
| `submission.csv` | Submissão no formato do Kaggle |
| `json/` | Um JSON por documento |
| `rastro.jsonl` | Uma linha por citação, com método de busca e de decisão |
| `scores.json` | Score por nível, macro-F1 e τ (só com `--avaliar`) |

Antes de terminar, o pipeline confere as invariantes de `docs/contratos.md`
e falha se alguma for quebrada. Com `--avaliar`, compara o resultado com
`baseline/scores.json` e avisa se algum nível piorou.

### 6. Parâmetros

Nem todos os parâmetros estão disponíveis nos dois ambientes. Os scripts Docker
(`run.sh` e `run.ps1`) aceitam apenas os parâmetros de dados e de execução. Os
demais valem só no desenvolvimento (`make`/`uv`); nos scripts Docker eles têm
valor fixo (as pastas `params/`, `oficiais/` e `baseline/` copiadas para a
imagem, e as pastas `out/` e `artifacts/` do repositório).

| Parâmetro | Padrão | Descrição | Scripts Docker | Desenvolvimento |
|---|---|---|---|---|
| `--txt` | `data/txt` | Pasta com os documentos `.txt` | Sim | Sim |
| `--db` | `data/desafio1_bracis.db` | Base SQLite de referência | Sim | Sim |
| `--gabarito` | `data/goldenset_offsets.csv` | Arquivo de gabarito para `--avaliar` | Sim | Sim |
| `--avaliar` | desligado | Calcula a métrica local com o gabarito; por padrão usa `data/goldenset_offsets.csv` | Sim | Sim |
| `--construir-catalogo` | desligado | Reconstrói o catálogo a partir da base | Automático quando o catálogo não existe | Sim |
| `--rebuild` | desligado | Reconstrói a imagem Docker | Sim | Não se aplica |
| `--saida` | `out` | Pasta de saída | Não | Sim |
| `--artifacts` | `artifacts` | Pasta onde o catálogo construído é salvo | Não | Sim |
| `--params` | `params` | Pasta da tabela de confiança | Não | Sim |
| `--oficiais` | `oficiais` | Pasta com os scripts oficiais do Kaggle | Não | Sim |
| `--baseline` | `baseline/scores.json` | Score de referência para o portão de regressão | Não | Sim |

Os caminhos marcados como padrão podem ser sobrescritos passando o parâmetro
explicitamente. Nos scripts Docker, só `--db`, `--txt` e `--gabarito`:

```bash
bash run.sh --db data/meu_banco.db --txt data/txt --gabarito outro/gabarito.csv --avaliar
```

Para alterar `--saida`, `--artifacts`, `--params`, `--oficiais` ou `--baseline`,
use o fluxo de desenvolvimento:

```bash
uv run python -m citacoes.rodar --db data/desafio1_bracis.db --txt data/txt --params outra_pasta
```

Ajuda completa: `uv run python -m citacoes.rodar --help`.

### 7. Testes e qualidade de código

```bash
uv run pytest                                   # make test
uv run ruff check src tests scripts             # make lint
uv run ruff format src tests scripts            # make format
uv run python -m citacoes.grafo.montagem        # make grafo: exporta docs/grafo.mmd
```

Avaliação isolada do nó de decisão (Módulo 4), onde `<pasta_dados>` é a pasta
que contém o arquivo `.db` e a subpasta `txt/`:

- `--modo isolado`: alimenta o nó de decisão diretamente com os spans do
  gabarito, sem depender dos módulos anteriores. Mede a qualidade da decisão
  em si.
- `--modo integrado`: roda o pipeline completo e avalia a decisão dentro do
  fluxo real, incluindo o impacto dos módulos de extração e busca.

```bash
uv run python scripts/avalia_decisao.py --dados <pasta_dados> --modo isolado
uv run python scripts/avalia_decisao.py --dados <pasta_dados> --modo integrado
```

## Abordagem

A solução é determinística: extração, normalização, busca no catálogo canônico
(SQLite FTS5) e decisão por heurística calibrada. Não usa modelos de linguagem
na execução, por isso não há pesos de modelos a baixar, e a execução roda
offline. Os detalhes estão em [docs/abordagem_entrega.md](docs/abordagem_entrega.md). 

## Documentação

Comece por [docs/arquitetura.md](docs/arquitetura.md). Os demais documentos
estão em [docs/](docs/): contratos, avaliação, decisões e reprodutibilidade.