#!/bin/bash
ROOT=$(pwd)
DB="data/desafio1_bracis.db"
TXT="data/txt"
GOLDEN=""
EVALUATE=false
EXTRA_ARGS=()
REBUILD=false


while [[ $# -gt 0 ]]; do
    case "$1" in
        --db)
            if [[ -z "$2" ]]; then
                echo "Erro: --db exige um caminho"
                exit 1
            fi
            DB="$2"
            shift 2
            ;;
        --txt)
            if [[ -z "$2" ]]; then
                echo "Erro: --txt exige um caminho"
                exit 1
            fi
            TXT="$2"
            shift 2
            ;;
        --gabarito)
            if [[ -z "$2" ]]; then
                echo "Erro: --gabarito exige um caminho"
                exit 1
            fi
            GOLDEN="$2"
            shift 2
            ;;
        --rebuild)
            REBUILD=true
            shift
            ;;
        --avaliar)
            EVALUATE=true
            EXTRA_ARGS+=("$1")
            shift
            ;;
        *)
            EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done

if [[ "$EVALUATE" == true && -z "$GOLDEN" ]]; then
    GOLDEN="data/goldenset_offsets.csv"
fi


if [ ! -f "$DB" ]; then
    echo "Erro: base nao encontrada: $DB"
    echo "Passe o caminho com: bash run.sh --db <caminho_db> --txt <pasta_txt>"
    echo "Ou coloque os dados em data/desafio1_bracis.db"
    exit 1
fi

if [ ! -d "$TXT" ]; then
    echo "Erro: pasta de .txt nao encontrada: $TXT"
    echo "Passe o caminho com: bash run.sh --db <caminho_db> --txt <pasta_txt>"
    echo "Ou coloque os dados em data/txt"
    exit 1
fi

DATA_DIR=$(cd "$(dirname "$DB")" && pwd)
TXT_DIR=$(cd "$TXT" && pwd)
DB_NAME=$(basename "$DB")

GOLDEN_MOUNT=()
GOLDEN_FLAG=()
if [[ -n "$GOLDEN" ]]; then
    if [ ! -f "$GOLDEN" ]; then
        echo "Erro: gabarito nao encontrado: $GOLDEN"
        echo "Passe o caminho com: bash run.sh --avaliar --gabarito <caminho_gabarito>"
        echo "Ou coloque o arquivo em data/goldenset_offsets.csv"
        exit 1
    fi
    GOLDEN_DIR=$(cd "$(dirname "$GOLDEN")" && pwd)
    GOLDEN_NAME=$(basename "$GOLDEN")
    GOLDEN_MOUNT=(-v "$GOLDEN_DIR":/app/golden:ro)
    GOLDEN_FLAG=(--gabarito "/app/golden/$GOLDEN_NAME")
fi

if [[ "$REBUILD" == true ]] || ! docker image inspect bracis-citacoes > /dev/null 2>&1; then
    docker build -t bracis-citacoes . || exit 1
fi

CATALOG_FLAG=()
if [ ! -f "$ROOT/artifacts/catalogo_canonico.json" ]; then
    CATALOG_FLAG=(--construir-catalogo)
fi

docker run \
  --rm \
  --network none \
  --cpus 8 \
  --memory 32g \
  -v "$DATA_DIR":/app/data \
  -v "$TXT_DIR":/app/data/txt \
  -v "$ROOT/artifacts":/app/artifacts \
  -v "$ROOT/out":/app/out \
  "${GOLDEN_MOUNT[@]}" \
  bracis-citacoes \
  uv run python -m citacoes.rodar \
    --db "/app/data/$DB_NAME" \
    --txt /app/data/txt \
    --saida /app/out \
    --oficiais /app/oficiais \
    "${CATALOG_FLAG[@]}" \
    "${GOLDEN_FLAG[@]}" \
    "${EXTRA_ARGS[@]}"