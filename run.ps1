<#
.SYNOPSIS
    One-command launcher for the AI Recruitment platform (Windows / PowerShell).

.DESCRIPTION
    Brings up the whole stack from a single terminal:
      1. Verifies .env exists
      2. Starts Docker Desktop if the daemon is down, waits for it
      3. docker compose up -d   (postgres, minio, redis, mailpit, elasticsearch, worker, beat)
      4. Waits for postgres to be healthy
      5. uv run alembic upgrade head
      6. Launches the FastAPI backend  (new window, port 8000)
      7. Launches the Vite frontend    (new window, port 3000)

    Backend and frontend open in their own windows so you can read their logs.
    Infra + worker + beat run as docker containers in the background.

.EXAMPLE
    .\run.ps1                # start everything
    .\run.ps1 -NoFrontend    # backend + infra only
    .\run.ps1 -InfraOnly     # just docker services (DB/MinIO/Redis/ES/Mailpit/worker)
#>
[CmdletBinding()]
param(
    [switch]$NoFrontend,
    [switch]$InfraOnly
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    [ok] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    [!]  $msg" -ForegroundColor Yellow }

# 1. .env
if (-not (Test-Path "$root\.env")) {
    Warn ".env not found - copying .env.example. Fill in secrets before real use."
    Copy-Item "$root\.env.example" "$root\.env"
}
Ok ".env present"

# 2. Docker daemon
Step "Checking Docker daemon"
$dockerUp = $false
try { docker info *> $null; if ($LASTEXITCODE -eq 0) { $dockerUp = $true } } catch {}
if (-not $dockerUp) {
    $dd = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dd) {
        Warn "Docker not running - launching Docker Desktop..."
        Start-Process $dd
    } else {
        throw "Docker daemon down and Docker Desktop not found. Start Docker manually."
    }
    $deadline = (Get-Date).AddMinutes(3)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        try { docker info *> $null; if ($LASTEXITCODE -eq 0) { $dockerUp = $true; break } } catch {}
        Write-Host "    waiting for docker..." -ForegroundColor DarkGray
    }
    if (-not $dockerUp) { throw "Docker did not become ready within 3 minutes." }
}
Ok "Docker is up"

# 3. Infra
Step "Starting infra (postgres, minio, redis, mailpit, elasticsearch, worker, beat)"
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

# 4. Wait for postgres healthy
Step "Waiting for postgres to be healthy"
$health = ""
$deadline = (Get-Date).AddMinutes(2)
while ((Get-Date) -lt $deadline) {
    $health = (docker inspect --format '{{.State.Health.Status}}' (docker compose ps -q postgres) 2>$null)
    if ($health -eq "healthy") { break }
    Start-Sleep -Seconds 2
}
if ($health -ne "healthy") { Warn "postgres not reporting healthy yet - continuing anyway" } else { Ok "postgres healthy" }

# 5. Migrations
Step "Applying database migrations (alembic upgrade head)"
uv run alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "alembic upgrade failed" }
Ok "migrations applied"

if ($InfraOnly) {
    Step "Infra-only mode - done."
    Write-Host "    MinIO console : http://localhost:9001" -ForegroundColor Gray
    Write-Host "    Mailpit       : http://localhost:8025" -ForegroundColor Gray
    return
}

# 6. Backend
Step "Launching backend (uvicorn :8000) in a new window"
Start-Process powershell -ArgumentList @(
    "-NoExit","-Command",
    "Set-Location '$root'; Write-Host 'BACKEND - http://localhost:8000/docs' -ForegroundColor Cyan; uv run uvicorn app.main:app --reload --port 8000"
)
Ok "backend starting"

# 7. Frontend
if (-not $NoFrontend) {
    Step "Launching frontend (vite :3000) in a new window"
    if (-not (Test-Path "$root\frontend\node_modules")) {
        Warn "frontend deps missing - running npm install first (this window)"
        Push-Location "$root\frontend"; npm install; Pop-Location
    }
    Start-Process powershell -ArgumentList @(
        "-NoExit","-Command",
        "Set-Location '$root\frontend'; Write-Host 'FRONTEND - http://localhost:3000' -ForegroundColor Cyan; npm run dev"
    )
    Ok "frontend starting"
}

Step "All set."
Write-Host ""
Write-Host "  Frontend     : http://localhost:3000" -ForegroundColor White
Write-Host "  API docs     : http://localhost:8000/docs" -ForegroundColor White
Write-Host "  MinIO console: http://localhost:9001" -ForegroundColor Gray
Write-Host "  Mailpit      : http://localhost:8025" -ForegroundColor Gray
Write-Host ""
Write-Host "  Stop everything: .\stop.ps1" -ForegroundColor DarkGray
