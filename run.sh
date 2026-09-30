#!/bin/bash
ROOT=$(pwd)

docker build -t bracis-citacoes .

if [ ! -f "$ROOT/artifacts/catalogo.json" ]; then
    EXTRA="--construir-catalogo"
else
    EXTRA=""
fi

docker run \
  --network none \
  --cpus 8 \
  --memory 32g \
  -v "$ROOT/data":/app/data \
  -v "$ROOT/artifacts":/app/artifacts \
  -v "$ROOT/out":/app/out \
  bracis-citacoes