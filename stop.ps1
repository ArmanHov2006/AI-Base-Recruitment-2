<#
.SYNOPSIS
    Stop the AI Recruitment stack.

.DESCRIPTION
    Stops host backend/frontend (uvicorn + vite) and the docker infra.

.EXAMPLE
    .\stop.ps1            # stop containers + host processes
    .\stop.ps1 -Volumes   # also delete docker volumes (wipes DB/MinIO/ES data)
#>
[CmdletBinding()]
param([switch]$Volumes)

$root = $PSScriptRoot
Set-Location $root

Write-Host "==> Stopping host backend/frontend" -ForegroundColor Cyan
# uvicorn runs as a python process; vite as node. Kill by command line match.
Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match "uvicorn app.main:app" -or $_.CommandLine -match "vite" } |
    ForEach-Object {
        Write-Host "    killing PID $($_.ProcessId): $($_.Name)" -ForegroundColor DarkGray
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Write-Host "==> Stopping docker infra" -ForegroundColor Cyan
if ($Volumes) {
    Write-Host "    -Volumes set: removing volumes (DB/MinIO/ES data WILL be wiped)" -ForegroundColor Yellow
    docker compose down -v
} else {
    docker compose down
}

Write-Host "Done." -ForegroundColor Green
