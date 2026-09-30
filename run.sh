#!/bin/bash
ROOT=$(pwd)
DB=${1:-"data/desafio1_bracis.db"}
TXT=${2:-"data/txt"}

if [ ! -f "$DB" ]; then
    echo "Erro: base não encontrada: $DB"
    echo "Passe o caminho com: bash run.sh <caminho_db> <pasta_txt>"
    echo "Ou coloque os dados em data/desafio1_bracis.db"
    exit 1
fi

if [ ! -d "$TXT" ]; then
    echo "Erro: pasta de .txt não encontrada: $TXT"
    echo "Passe o caminho com: bash run.sh <caminho_db> <pasta_txt>"
    echo "Ou coloque os dados em data/txt"
    exit 1
fi

DATA_DIR=$(cd "$(dirname "$DB")" && pwd)
TXT_DIR=$(cd "$TXT" && pwd)
DB_NOME=$(basename "$DB")

if ! docker image inspect bracis-citacoes > /dev/null 2>&1; then
    docker build -t bracis-citacoes .
fi

if [ ! -f "$ROOT/artifacts/catalogo.json" ]; then
    CATALOGO="--construir-catalogo"
else
    CATALOGO=""
fi

docker run \
  --network none \
  --cpus 8 \
  --memory 32g \
  -v "$DATA_DIR":/app/data \
  -v "$TXT_DIR":/app/data/txt \
  -v "$ROOT/artifacts":/app/artifacts \
  -v "$ROOT/out":/app/out \
  bracis-citacoes \
  uv run python -m citacoes.rodar \
    --db /app/data/$DB_NOME \
    --txt /app/data/txt \
    --saida /app/out \
    --oficiais /app/oficiais \
    $CATALOGO \
    "${@:3}"