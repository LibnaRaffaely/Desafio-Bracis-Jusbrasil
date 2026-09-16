.PHONY: setup setup-llm check-data test lint format

setup:        ## ambiente base
	uv sync

setup-llm:    ## ambiente + agentes LLM (compila o llama.cpp)
	uv sync --extra llm

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
