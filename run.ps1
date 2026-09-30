param(
    [Parameter(ValueFromRemainingArguments)][string[]]$ExtraArgs
)

$ROOT = $PWD

docker image inspect bracis-citacoes | Out-Null
if ($LASTEXITCODE -ne 0) {
    docker build -t bracis-citacoes .
}

if (-not (Test-Path "$ROOT/artifacts/catalogo.json")) {
    $EXTRA = "--construir-catalogo"
} else {
    $EXTRA = ""
}

docker run `
  --network none `
  --cpus 8 `
  --memory 32g `
  -v "${ROOT}/data:/app/data" `
  -v "${ROOT}/artifacts:/app/artifacts" `
  -v "${ROOT}/out:/app/out" `
  bracis-citacoes `
  uv run python -m citacoes.rodar `
    --txt /app/data/txt `
    --saida /app/out `
    --oficiais /app/oficiais `
    --db /app/data/desafio1_bracis.db `
    $EXTRA `
    @ExtraArgs