[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Banco = "",
    [string]$Txts = "",
    [Parameter(ValueFromRemainingArguments)][string[]]$ExtraArgs
)

$ROOT = $PWD.Path
$Golden = ""
$Forward = @()
$Evaluate = $false
$Rebuild = $false
if (-not $ExtraArgs) { $ExtraArgs = @() }

function Fail($message) {
    Write-Host $message -ForegroundColor Red
    exit 1
}

$i = 0
while ($i -lt $ExtraArgs.Count) {
    $arg = $ExtraArgs[$i]
    switch ($arg) {
        { $_ -in "--db", "--txt", "--gabarito" } {
            if ($i + 1 -ge $ExtraArgs.Count) { Fail "Erro: $arg exige um caminho" }
            $value = $ExtraArgs[$i + 1]
            if ($arg -eq "--db")       { $Banco = $value }
            elseif ($arg -eq "--txt")  { $Txts = $value }
            else                       { $Golden = $value }
            $i += 2
        }
        "--rebuild" {
            $Rebuild = $true
            $i += 1
        }
        "--avaliar" {
            $Evaluate = $true
            $Forward += $arg
            $i += 1
        }
        default {
            $Forward += $arg
            $i += 1
        }
    }
}

if (-not $Banco) { $Banco = "data\desafio1_bracis.db" }
if (-not $Txts)  { $Txts = "data\txt" }

if ($Evaluate -and -not $Golden) { $Golden = "data\goldenset_offsets.csv" }

if (-not (Test-Path $Banco -PathType Leaf)) {
    Fail "Erro: base não encontrada: $Banco`nPasse o caminho com: .\run.ps1 --db <caminho_db> --txt <pasta_txt>`nOu coloque os dados em data\desafio1_bracis.db"
}
if (-not (Test-Path $Txts -PathType Container)) {
    Fail "Erro: pasta de .txt não encontrada: $Txts`nPasse o caminho com: .\run.ps1 --db <caminho_db> --txt <pasta_txt>`nOu coloque os dados em data\txt"
}

$DbAbs = (Get-Item $Banco).FullName
$TxtAbs = (Get-Item $Txts).FullName
$DataDir = Split-Path $DbAbs -Parent
$DbName = Split-Path $DbAbs -Leaf

# Golden set: mounted in its own volume, so it can live in any folder
$GoldenMount = @()
$GoldenFlag = @()
if ($Golden) {
    if (-not (Test-Path $Golden -PathType Leaf)) {
        Fail "Erro: gabarito não encontrado: $Golden`nPasse o caminho com: .\run.ps1 --avaliar --gabarito <caminho_gabarito>`nOu coloque o arquivo em data\goldenset_offsets.csv"
    }
    $GoldenAbs = (Get-Item $Golden).FullName
    $GoldenDir = Split-Path $GoldenAbs -Parent
    $GoldenName = Split-Path $GoldenAbs -Leaf
    $GoldenMount = @("-v", "${GoldenDir}:/app/golden:ro")
    $GoldenFlag = @("--gabarito", "/app/golden/$GoldenName")
}

docker image inspect bracis-citacoes *> $null
if ($Rebuild -or $LASTEXITCODE -ne 0) {
    docker build -t bracis-citacoes .
    if ($LASTEXITCODE -ne 0) { Fail "Erro: falha ao construir a imagem Docker" }
}


$CatalogFlag = @()
if (-not (Test-Path "$ROOT\artifacts\catalogo_canonico.json")) { $CatalogFlag = @("--construir-catalogo") }

$DockerArgs = @(
    "run",
    "--network", "none",
    "--cpus", "8",
    "--memory", "32g",
    "-v", "${DataDir}:/app/data",
    "-v", "${TxtAbs}:/app/data/txt",
    "-v", "${ROOT}/artifacts:/app/artifacts",
    "-v", "${ROOT}/out:/app/out"
) + $GoldenMount + @(
    "bracis-citacoes",
    "uv", "run", "python", "-m", "citacoes.rodar",
    "--db", "/app/data/$DbName",
    "--txt", "/app/data/txt",
    "--saida", "/app/out",
    "--oficiais", "/app/oficiais"
) + $CatalogFlag + $GoldenFlag + $Forward

& docker @DockerArgs
exit $LASTEXITCODE