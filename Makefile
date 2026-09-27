.PHONY: setup setup-llm check-data test lint format rodar grafo

setup:        ## ambiente base
	uv sync

setup-llm:    ## ambiente + agentes LLM (compila o llama.cpp)
	uv sync --extra llm

DADOS ?= data

rodar:        ## gera out/submission.csv (ex.: make rodar ARGS="--avaliar")
	uv run python -m citacoes.rodar --txt $(DADOS)/txt --saida out --oficiais $(DADOS) \
		--db $(DADOS)/desafio1_bracis.db --gabarito $(DADOS)/goldenset.csv $(ARGS)

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
