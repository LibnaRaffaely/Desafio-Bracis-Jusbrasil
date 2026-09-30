param(
    [string]$Banco = "",
    [string]$Txts = "",
    [Parameter(ValueFromRemainingArguments)][string[]]$ExtraArgs
)

$ROOT = $PWD

if (-not $Banco) { $Banco = "data\desafio1_bracis.db" }
if (-not $Txts) { $Txts = "data\txt" }


if (-not (Test-Path $Banco)) {
    Write-Error "Erro: base não encontrada: $Banco"
    Write-Error "Passe o caminho com: .\run.ps1 -Banco <caminho_db> -Txts <pasta_txt>"
    Write-Error "Ou coloque os dados em data\desafio1_bracis.db"
    exit 1
}

if (-not (Test-Path $Txts)) {
    Write-Error "Erro: pasta de .txt não encontrada: $Txts"
    Write-Error "Passe o caminho com: .\run.ps1 -Banco <caminho_db> -Txts <pasta_txt>"
    Write-Error "Ou coloque os dados em data\txt"
    exit 1
}


$BancoAbs = (Get-Item $Banco).FullName
$TxtsAbs = (Get-Item $Txts).FullName
$BancoDir = Split-Path $BancoAbs -Parent
$BancoNome = Split-Path $BancoAbs -Leaf

docker image inspect bracis-citacoes | Out-Null
if ($LASTEXITCODE -ne 0) {
    docker build -t bracis-citacoes .
}

$CATALOGO = if (-not (Test-Path "$ROOT/artifacts/catalogo.json")) { "--construir-catalogo" } else { "" }

docker run `
  --network none `
  --cpus 8 `
  --memory 32g `
  -v "${BancoDir}:/app/data" `
  -v "${TxtsAbs}:/app/data/txt" `
  -v "${ROOT}/artifacts:/app/artifacts" `
  -v "${ROOT}/out:/app/out" `
  bracis-citacoes `
  uv run python -m citacoes.rodar `
    --db /app/data/$BancoNome `
    --txt /app/data/txt `
    --saida /app/out `
    --oficiais /app/oficiais `
    $CATALOGO `
    @ExtraArgs