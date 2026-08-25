<#
    Gera o executavel do PyAgent IA e monta a pasta de distribuicao.

    Uso:
        .\build.ps1
        .\build.ps1 -Limpar      # recria a venv de build do zero

    Resultado: dist\PyAgentIA\ pronta para copiar para o servidor.

    Observacao: este arquivo e mantido em ASCII puro de proposito. O Windows
    PowerShell 5.1 le scripts .ps1 como ANSI, e acentos gravados em UTF-8 sem BOM
    viram erro de parse.
#>

param(
    [switch]$Limpar
)

$ErrorActionPreference = "Stop"
$raiz = $PSScriptRoot

# O Windows PowerShell 5.1 transforma cada linha de stderr de um executavel nativo
# em ErrorRecord, o que com ErrorActionPreference=Stop aborta o script mesmo quando
# o processo termina com codigo 0. PyInstaller e o pip escrevem progresso em stderr,
# entao as chamadas nativas passam por aqui e sao avaliadas pelo codigo de saida.
function Invoke-Nativo {
    param(
        [string]$Descricao,
        [scriptblock]$Comando
    )
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Comando 2>&1 | ForEach-Object { Write-Host $_ }
    } finally {
        $ErrorActionPreference = $anterior
    }
    if ($LASTEXITCODE -ne 0) {
        throw "$Descricao falhou (codigo de saida $LASTEXITCODE)"
    }
}
Set-Location $raiz

$venv = Join-Path $raiz ".venv-build"
$pacote = Join-Path $raiz "dist\PyAgentIA"

Write-Host "=== PyAgent IA - build do executavel ===" -ForegroundColor Cyan

if ($Limpar -and (Test-Path $venv)) {
    Write-Host "Removendo venv de build anterior..." -ForegroundColor Yellow
    Remove-Item $venv -Recurse -Force
}

# 1. Ambiente isolado. Sem isso o PyInstaller arrasta os pacotes globais
#    e o executavel passa de 300 MB.
if (-not (Test-Path $venv)) {
    Write-Host "[1/5] Criando ambiente virtual de build..." -ForegroundColor Green
    Invoke-Nativo "Criacao da venv" { python -m venv $venv }
} else {
    Write-Host "[1/5] Reaproveitando ambiente virtual existente." -ForegroundColor Green
}

$py = Join-Path $venv "Scripts\python.exe"

Write-Host "[2/5] Instalando dependencias..." -ForegroundColor Green
Invoke-Nativo "Atualizacao do pip" { & $py -m pip install --upgrade pip --quiet }
Invoke-Nativo "Instalacao das dependencias" { & $py -m pip install -r (Join-Path $raiz "requirements-build.txt") --quiet }

Write-Host "[3/5] Limpando artefatos anteriores..." -ForegroundColor Green
foreach ($pasta in @("build", "dist")) {
    $alvo = Join-Path $raiz $pasta
    if (Test-Path $alvo) { Remove-Item $alvo -Recurse -Force }
}

Write-Host "[4/5] Compilando com PyInstaller..." -ForegroundColor Green
Invoke-Nativo "PyInstaller" { & $py -m PyInstaller (Join-Path $raiz "pyagent.spec") --clean --noconfirm }

Write-Host "[5/5] Montando a pasta de distribuicao..." -ForegroundColor Green
New-Item -ItemType Directory -Force -Path $pacote | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $pacote "ai_context") | Out-Null

Move-Item (Join-Path $raiz "dist\PyAgentIA.exe") $pacote -Force
Copy-Item (Join-Path $raiz "config.ini.example") (Join-Path $pacote "config.ini") -Force
Copy-Item (Join-Path $raiz "app\ai_context\exemplos_treinamento.md") (Join-Path $pacote "ai_context") -Force
Copy-Item (Join-Path $raiz "app\ai_context\regras_projeto.example.md") (Join-Path $pacote "ai_context\regras_projeto.md") -Force

if (Test-Path (Join-Path $raiz "DEPLOY.md")) {
    Copy-Item (Join-Path $raiz "DEPLOY.md") $pacote -Force
}

$bytes = (Get-Item (Join-Path $pacote "PyAgentIA.exe")).Length
$tamanho = [math]::Round($bytes / 1MB, 1)

Write-Host ""
Write-Host "Build concluido." -ForegroundColor Cyan
Write-Host ("  Executavel: {0}\PyAgentIA.exe ({1} MB)" -f $pacote, $tamanho)
Write-Host ""
Write-Host "Proximos passos:" -ForegroundColor Yellow
Write-Host ("  1. Preencha {0}\config.ini (chaves de API e credenciais do Bitbucket)" -f $pacote)
Write-Host ("  2. Ajuste {0}\ai_context\regras_projeto.md com as regras do sistema" -f $pacote)
Write-Host ("  3. Copie a pasta {0} para o servidor e execute PyAgentIA.exe" -f $pacote)
