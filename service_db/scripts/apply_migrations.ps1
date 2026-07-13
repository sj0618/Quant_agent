param(
    [string]$Service = "db",
    [string]$DatabaseName = $(if ($env:QUANT_DB_NAME) { $env:QUANT_DB_NAME } else { "quant_agent" }),
    [string]$DatabaseUser = $(if ($env:QUANT_DB_USER) { $env:QUANT_DB_USER } else { "quant_agent" }),
    [int]$HealthRetries = 30,
    [int]$HealthSleepSeconds = 2
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found. Install Docker Desktop or make sure '$Name' is on PATH."
    }
}

$serviceDbRoot = Split-Path -Parent $PSScriptRoot
$repositoryRoot = Split-Path -Parent $serviceDbRoot
$migrationPath = Join-Path $serviceDbRoot "migrations"
$composeFile = Join-Path $repositoryRoot "DE/compose.yaml"

Require-Command "docker"

# Keep credentials in the current shell/CI secret store. Do not load repository .env files.
$env:COMPOSE_DISABLE_ENV_FILE = "1"

if (-not $env:QUANT_DB_PASSWORD) {
    throw "QUANT_DB_PASSWORD is required in the current shell. Do not store it in .env."
}

if (-not (Test-Path -LiteralPath $composeFile)) {
    throw "DE Docker Compose file not found: $composeFile"
}

$migrationFiles = Get-ChildItem -LiteralPath $migrationPath -Filter "*.sql" | Sort-Object Name
if ($migrationFiles.Count -eq 0) {
    throw "No service DB migration SQL files found under: $migrationPath"
}

Write-Host "Starting shared local database service '$Service' with DE/compose.yaml..."
docker compose -f $composeFile up -d $Service
if ($LASTEXITCODE -ne 0) {
    throw "Failed to start database service '$Service'."
}

Write-Host "Waiting for PostgreSQL readiness..."
$ready = $false
for ($attempt = 1; $attempt -le $HealthRetries; $attempt++) {
    docker compose -f $composeFile exec -T $Service pg_isready -U $DatabaseUser -d $DatabaseName *> $null
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds $HealthSleepSeconds
}

if (-not $ready) {
    throw "Database service '$Service' did not become ready after $HealthRetries attempts."
}

$containerId = (docker compose -f $composeFile ps -q $Service).Trim()
if (-not $containerId) {
    throw "Could not resolve the running container for service '$Service'."
}

foreach ($migrationFile in $migrationFiles) {
    $containerMigrationPath = "/tmp/service_db_$($migrationFile.Name)"
    Write-Host "Applying service DB migration '$($migrationFile.Name)' to '$DatabaseName'..."

    docker cp $migrationFile.FullName "${containerId}:$containerMigrationPath"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to copy migration '$($migrationFile.Name)' into the database container."
    }

    docker compose -f $composeFile exec -T $Service psql `
        -v ON_ERROR_STOP=1 `
        -U $DatabaseUser `
        -d $DatabaseName `
        -f $containerMigrationPath

    if ($LASTEXITCODE -ne 0) {
        throw "Migration '$($migrationFile.Name)' failed with exit code $LASTEXITCODE."
    }
}

Write-Host "Service DB migrations applied successfully."
