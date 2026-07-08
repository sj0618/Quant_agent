param(
    [string]$Service = "db",
    [string]$DatabaseName = $(if ($env:QUANT_DB_NAME) { $env:QUANT_DB_NAME } else { "quant_agent" }),
    [string]$DatabaseUser = $(if ($env:QUANT_DB_USER) { $env:QUANT_DB_USER } else { "quant_agent" }),
    [string]$MigrationPath = "migrations",
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

Require-Command "docker"

# Prevent Docker Compose from implicitly reading the repository .env file.
# Secrets must come from the current shell, Docker/OS secret stores, or CI.
$env:COMPOSE_DISABLE_ENV_FILE = "1"

if (-not $env:QUANT_DB_PASSWORD) {
    throw "QUANT_DB_PASSWORD is required in the current shell. Do not store it in .env."
}

if (-not (Test-Path -LiteralPath $MigrationPath)) {
    throw "Migration path not found: $MigrationPath"
}

if ((Get-Item -LiteralPath $MigrationPath).PSIsContainer) {
    $migrationFiles = Get-ChildItem -LiteralPath $MigrationPath -Filter "*.sql" | Sort-Object Name
} else {
    $migrationFiles = @(Get-Item -LiteralPath $MigrationPath)
}

if ($migrationFiles.Count -eq 0) {
    throw "No migration SQL files found under: $MigrationPath"
}

Write-Host "Starting database service '$Service'..."
docker compose up -d $Service

Write-Host "Waiting for PostgreSQL readiness..."
$ready = $false
for ($attempt = 1; $attempt -le $HealthRetries; $attempt++) {
    docker compose exec -T $Service pg_isready -U $DatabaseUser -d $DatabaseName *> $null
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds $HealthSleepSeconds
}

if (-not $ready) {
    throw "Database service '$Service' did not become ready after $HealthRetries attempts."
}

foreach ($migrationFile in $migrationFiles) {
    $containerMigrationPath = "/migrations/$($migrationFile.Name)"
    Write-Host "Applying migration '$containerMigrationPath' to database '$DatabaseName'..."
    docker compose exec -T $Service psql `
        -v ON_ERROR_STOP=1 `
        -U $DatabaseUser `
        -d $DatabaseName `
        -f $containerMigrationPath

    if ($LASTEXITCODE -ne 0) {
        throw "Migration '$($migrationFile.Name)' failed with exit code $LASTEXITCODE."
    }
}

Write-Host "Migrations applied successfully."
