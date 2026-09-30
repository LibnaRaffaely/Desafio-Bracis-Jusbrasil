$ROOT = $PWD

$exists = docker image inspect bracis-citacoes 2>$null
if (-not $exists) {
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
  bracis-citacoes