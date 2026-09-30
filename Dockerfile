
FROM python:3.12-slim

# UV
COPY --from=ghcr.io/astral-sh/uv:0.5.0 /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_NO_SYNC=1
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/src

# dependências
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

# código fonte e parâmetros
COPY src/ src/
COPY params/ params/
COPY scripts/ scripts/
COPY Makefile ./
COPY oficiais/ oficiais/

# dados
VOLUME ["/app/data", "/app/artifacts", "/app/out"]

# Reproduzindo a submissão: 
CMD ["uv", "run", "python", "-m", "citacoes.rodar", \
     "--txt", "data/txt", \
     "--saida", "out", \
     "--oficiais", "oficiais", \
     "--db", "data/desafio1_bracis.db"]