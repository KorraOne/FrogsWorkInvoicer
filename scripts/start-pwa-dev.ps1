# Start PWA static server + API worker for local mobile testing.
param(
    [int]$PwaPort = 8090,
    [int]$ApiPort = 8787
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pwa = Join-Path $root "client_web"
$worker = Join-Path $root "account_api\worker"
$schema = Join-Path $root "account_api\schema.sql"
$devVars = Join-Path $worker ".dev.vars"

function Stop-PortListener {
    param([int]$Port)
    $procIds = @()
    netstat -ano | Select-String ":$Port\s" | ForEach-Object {
        $parts = ($_ -split '\s+') | Where-Object { $_ -ne '' }
        $procId = $parts[-1]
        if ($procId -match '^\d+$' -and [int]$procId -gt 0) {
            $procIds += [int]$procId
        }
    }
    foreach ($procId in ($procIds | Select-Object -Unique)) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "PWA:  http://127.0.0.1:$PwaPort"
Write-Host "API:  http://127.0.0.1:$ApiPort (Cloudflare Worker via wrangler dev)"
Write-Host ""
Write-Host "The PWA auto-uses http://127.0.0.1:$ApiPort when opened on localhost."
Write-Host ""

Push-Location $worker
if (-not (Test-Path "node_modules")) {
    npm install
}

Set-Content -Path $devVars -Value "JWT_SECRET=dev-jwt-secret-change-in-production" -Encoding utf8NoBOM
Write-Host "Ensured $devVars contains JWT_SECRET."

Write-Host "Stopping any process already listening on port $ApiPort..."
Stop-PortListener -Port $ApiPort
Start-Sleep -Seconds 1

Write-Host "Applying local D1 schema (idempotent)..."
npx wrangler d1 execute frogswork-account --local --file=$schema
if ($LASTEXITCODE -ne 0) {
    throw "Local D1 schema apply failed. Is wrangler installed?"
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$worker'; npx wrangler dev --port $ApiPort"
Pop-Location

Write-Host "Waiting for API worker..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 2
        if ($health.ok) { $ready = $true; break }
    } catch {
        continue
    }
}
if (-not $ready) {
    Write-Warning "API did not respond on port $ApiPort yet. Check the Wrangler terminal window."
} else {
    Write-Host "API is ready."
}

Push-Location $pwa
if (-not (Test-Path "icons\icon-192.png")) {
    New-Item -ItemType Directory -Force -Path "icons" | Out-Null
    $src = Join-Path $root "marketing_site\assets\brand\favicon-48.png"
    Copy-Item $src "icons\icon-192.png" -Force
    Copy-Item $src "icons\icon-512.png" -Force
}
python -m http.server $PwaPort
