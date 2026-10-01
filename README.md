# Desafio BRACIS – JusBrasil

Verificador de citações jurídicas para o Desafio BRACIS 2026 (JusBrasil).
Pipeline híbrido orquestrado com LangGraph: nós determinísticos de extração,
normalização, busca em catálogo canônico (chave normalizada, construído a partir
da base SQLite) e decisão por
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
Todos os argumentos são opcionais e podem ser passados em qualquer ordem.
Sem `--db` e `--txt`, os scripts usam os dados da pasta `data/`
(conforme o `data/README.md`).

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

Todos os parâmetros estão na [tabela de parâmetros](#6-parâmetros). 
A coluna "Scripts Docker" indica quais funcionam nos scripts `run.sh` e `run.ps1`.


> **NOTA**:
> A imagem Docker só é construída se ainda não existir. É necessário `--rebuild` para
> reconstruí-la em caso de alteração em `src/`, `scripts/`, `oficiais/`, `baseline/`,
> `params/` ou as dependências (`pyproject.toml` e `uv.lock`).
>  O `--rebuild` também executa o pipeline em
> seguida, então exige `--db` e `--txt` (ou os dados em `data/`).

> **NOTA**:
> Os scripts só passam `--construir-catalogo` sozinhos quando `artifacts/` não tem
> catálogo. Se a base mudar, ou se o catálogo vier de uma versão anterior sem o hash
> do `.db` (`artifacts/catalogo_canonico.db.sha256`), o pipeline para com a mensagem
> "O catálogo ... não corresponde à base ...". Nesse caso, rode de novo com
> `--construir-catalogo` (por exemplo, `.\run.ps1 --avaliar --construir-catalogo`).


### 4. Desenvolvimento

> **NOTA**:
> O Makefile usa a pasta `data/` por padrão (altere com `DADOS=<pasta>`, por exemplo
> `make rodar DADOS=outra_pasta`). Preencha-a conforme o `data/README.md` antes de
> rodar qualquer comando.

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
`baseline/scores.json` e avisa se algum nível piorou. O relatório de erros
por citação (`erros.csv`, previsto em `docs/avaliacao.md`) não é gerado
nesta versão.

### 6. Parâmetros

Os scripts Docker (`run.sh` e `run.ps1`) aceitam apenas os parâmetros de dados e de execução. 
Os demais valem só no desenvolvimento; nos scripts Docker eles têm
valor fixo (as pastas `params/`, `oficiais/` e `baseline/` copiadas para a
imagem, e as pastas `out/` e `artifacts/` do repositório).

| Parâmetro | Padrão | Descrição | Scripts Docker | Desenvolvimento |
|---|---|---|---|---|
| `--txt` | `data/txt` | Pasta com os documentos `.txt` | Sim | Sim |
| `--db` | `data/desafio1_bracis.db` | Base SQLite de referência | Sim | Sim |
| `--gabarito` | `data/goldenset_offsets.csv` | Arquivo de gabarito para `--avaliar` | Sim | Sim |
| `--avaliar` | desligado | Calcula a métrica local com o gabarito; por padrão usa `data/goldenset_offsets.csv` | Sim | Sim |
| `--rebuild` | desligado | Reconstrói a imagem Docker | Sim | Não se aplica |
| `--saida` | `out` | Pasta de saída | Não | Sim |
| `--artifacts` | `artifacts` | Pasta onde o catálogo construído é salvo | Não | Sim |
| `--params` | `params` | Pasta da tabela de confiança | Não | Sim |
| `--oficiais` | `oficiais` | Pasta com os scripts oficiais do Kaggle | Não | Sim |
| `--baseline` | `baseline/scores.json` | Score de referência para o portão de regressão | Não | Sim |
| `--construir-catalogo` | desligado | Reconstrói o catálogo a partir da base. Obrigatório quando o `.db` muda | Automático quando o catálogo não existe | Sim |

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

## Organização do repositório

```
src/citacoes/   código do pipeline (grafo, nós, catálogo, domínio, avaliação); ponto de entrada em rodar.py
params/         tabela de confiança calibrada (vai para a imagem Docker)
oficiais/       scripts oficiais do desafio: json_to_submission.py e kaggle_metric.py
baseline/       scores de referência para o portão de regressão
scripts/        utilitários: checagem dos dados, ajuste da confiança, avaliação da extração e da decisão
tests/          testes (pytest)
docs/           arquitetura, contratos, avaliação, decisões, abordagem
notebooks/      exploração
data/           dados da competição (fora do git, ver data/README.md)
artifacts/      catálogo canônico construído e hash do .db de origem (gerado, fora do git)
out/            saídas de cada execução (gerado, fora do git)
run.sh, run.ps1, Dockerfile, Makefile
```

A pasta `oficiais/` guarda, sem alteração, os scripts fornecidos pela organização
do desafio. Eles ficam versionados porque não contêm dados sensíveis e são
usados pela solução: `json_to_submission.py` converte os JSON por documento no
`submission.csv`, e `kaggle_metric.py` calcula o score local com `--avaliar`.
A imagem Docker copia a pasta, e o caminho pode ser trocado com `--oficiais`
no fluxo de desenvolvimento.

## Abordagem

A solução é determinística: extração por regras, normalização, busca no catálogo canônico (chave normalizada, construído a partir da base SQLite) e decisão pela cardinalidade de candidatos, com confiança calibrada por tabela. Não usa modelos de linguagem na execução, por isso não há pesos de modelos a baixar, e a execução roda offline.

No dev set (26 documentos, 192 citações), o score final é 1,0998 (teto 1,1), com macro-F1 1,0 e τ = 0 nos dois níveis. A construção do catálogo leva cerca de 20 s e uma execução completa, menos de 1 minuto.

O resumo das principais decisões, os resultados e as limitações estão em [docs/abordagem_entrega.md](docs/abordagem_entrega.md); o registro de cada decisão, em [docs/decisoes.md](docs/decisoes.md).

## Documentação

Comece por [docs/arquitetura.md](docs/arquitetura.md). Os demais documentos
estão em [docs/](docs/): contratos, avaliação, decisões e reprodutibilidade.
