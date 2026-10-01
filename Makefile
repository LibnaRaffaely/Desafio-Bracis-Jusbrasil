.PHONY: setup setup-llm check-data test lint format rodar calibrar grafo

setup:        ## ambiente base
	uv sync --frozen

setup-llm:    ## ambiente + agentes LLM (compila o llama.cpp)
	uv sync --extra llm

DADOS ?= data

rodar:        ## gera out/submission.csv (ex.: make rodar ARGS="--avaliar")
	uv run python -m citacoes.rodar --txt $(DADOS)/txt --saida out --oficiais oficiais \
		--db $(DADOS)/desafio1_bracis.db --gabarito $(DADOS)/goldenset_offsets.csv $(ARGS)

calibrar:     ## ajusta params/tabela_confianca.json com a última rodada (rode make rodar antes)
	uv run python scripts/ajustar_confianca.py --rastro out/rastro.jsonl --gabarito $(DADOS)/goldenset_offsets.csv --destino params/tabela_confianca.json

grafo:        ## exporta o diagrama do grafo para docs/grafo.mmd
	uv run python -m citacoes.grafo.montagem

check-data:   ## confere os dados em ./data
	uv run python scripts/check_data.py data

test:
	uv run pytest

lint:
	uv run ruff check src tests scripts
	uv run ruff format --check src tests scripts

format:
	uv run ruff check --fix src tests scripts
	uv run ruff format src tests scripts
