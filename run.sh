#!/bin/bash
DB=$1
TXT=$2

docker build -t bracis-citacoes .

if [ ! -f "artifacts/catalogo.json" ]; then
    ARGS="--construir-catalogo"
else
    ARGS=""
fi


docker run \
  --network none \
  --cpus 8 \
  --memory 32g \
  -v $(pwd)/data:/app/data \
  -v $(realpath $TXT):/app/data/txt \
  -v $(pwd)/out:/app/out \
  bracis-citacoes \
  uv run python -m citacoes.rodar \
    --db /app/data/$(basename $DB) \
    --txt /app/data/txt \
    --saida /app/out \
    --oficiais /app/data \
    --construir-catalogo