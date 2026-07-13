$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$deRoot = Join-Path $repositoryRoot "DE"
$deScript = Join-Path $deRoot "scripts/apply_migrations.ps1"
$serviceDbScript = Join-Path $repositoryRoot "service_db/scripts/apply_migrations.ps1"

if (-not $env:QUANT_DB_PASSWORD) {
    throw "QUANT_DB_PASSWORD is required in the current shell. Do not store it in .env."
}

Write-Host "Applying DE migrations..."
Push-Location $deRoot
try {
    & $deScript
} finally {
    Pop-Location
}

Write-Host "Applying service DB migrations..."
& $serviceDbScript

Write-Host "All migrations applied successfully."
