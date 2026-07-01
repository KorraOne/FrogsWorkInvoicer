# First-time D1 setup for api.frogswork.com (run from repo root in an interactive terminal).
# Prerequisite: npx wrangler login   OR   set CLOUDFLARE_API_TOKEN (+ CLOUDFLARE_ACCOUNT_ID)
#
# Usage:
#   .\scripts\setup-d1-production.ps1
#   .\scripts\setup-d1-production.ps1 -DatabaseId "your-uuid-here"   # skip create/list
#   .\scripts\setup-d1-production.ps1 -SkipDeploy                      # schema only

param(
    [string]$DatabaseId = "",
    [string]$DatabaseName = "frogswork-account",
    [switch]$SkipDeploy,
    [switch]$SkipCreate
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$WorkerDir = Join-Path $Root "account_api\worker"
$WranglerToml = Join-Path $WorkerDir "wrangler.toml"
$SchemaFile = Join-Path $Root "account_api\schema.sql"

function Ensure-WranglerAuth {
    Push-Location $WorkerDir
    try {
        $whoami = npx wrangler whoami 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0 -or $whoami -match "not authenticated|CLOUDFLARE_API_TOKEN") {
            throw @"
Wrangler is not authenticated. In this terminal run:
  cd account_api\worker
  npx wrangler login
Or set CLOUDFLARE_API_TOKEN (and CLOUDFLARE_ACCOUNT_ID if needed).
See https://developers.cloudflare.com/workers/wrangler/commands/#login
"@
        }
        Write-Host $whoami.Trim()
    } finally {
        Pop-Location
    }
}

function Set-WranglerDatabaseId {
    param([string]$Id)
    if ($Id -match "^00000000-0000-0000-0000-000000000000$") {
        throw "Refusing to write placeholder database_id."
    }
    $raw = Get-Content $WranglerToml -Raw
    $updated = $raw -replace 'database_id = "[^"]+"', "database_id = `"$Id`""
    if ($updated -eq $raw) {
        throw "Could not patch database_id in wrangler.toml"
    }
    Set-Content -Path $WranglerToml -Value $updated -NoNewline
    Write-Host "Updated wrangler.toml database_id = $Id"
}

function Get-OrCreate-DatabaseId {
    Push-Location $WorkerDir
    try {
        if (-not $SkipCreate) {
            $listJson = npx wrangler d1 list --json 2>&1
            if ($LASTEXITCODE -eq 0 -and $listJson) {
                $databases = $listJson | ConvertFrom-Json
                $existing = $databases | Where-Object { $_.name -eq $DatabaseName }
                if ($existing) {
                    $id = $existing.uuid
                    Write-Host "Found existing D1 database '$DatabaseName' -> $id"
                    return $id
                }
            }
            Write-Host "Creating D1 database '$DatabaseName'..."
            $createOut = npx wrangler d1 create $DatabaseName 2>&1 | Out-String
            Write-Host $createOut
            if ($createOut -match "database_id\s*=\s*[`"']?([0-9a-f-]{36})") {
                return $Matches[1]
            }
            if ($createOut -match "([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})") {
                return $Matches[1]
            }
            throw "Could not parse database_id from wrangler d1 create output."
        }
        throw "No -DatabaseId provided and -SkipCreate was set."
    } finally {
        Pop-Location
    }
}

function Invoke-SchemaMigrate {
    Push-Location $WorkerDir
    try {
        Write-Host "Applying schema to remote D1..."
        npx wrangler d1 execute $DatabaseName --remote --file=$SchemaFile
        if ($LASTEXITCODE -ne 0) { throw "d1 execute failed." }
        Write-Host "Verifying tables..."
        npx wrangler d1 execute $DatabaseName --remote --command "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        if ($LASTEXITCODE -ne 0) { throw "d1 verify failed." }
    } finally {
        Pop-Location
    }
}

function Invoke-WorkerDeploy {
    Push-Location $WorkerDir
    try {
        Write-Host "Deploying account API Worker..."
        npm run deploy
        if ($LASTEXITCODE -ne 0) { throw "npm run deploy failed." }
    } finally {
        Pop-Location
    }
}

function Test-ApiHealth {
    try {
        $resp = Invoke-RestMethod -Uri "https://api.frogswork.com/health" -TimeoutSec 15
        Write-Host "GET /health -> $($resp | ConvertTo-Json -Compress)"
    } catch {
        Write-Warning "GET /health failed: $_"
    }
}

function Test-TelemetryHeartbeat {
    $installId = ("a" * 64)
    $body = @{
        install_id = $installId
        app_version = "2.0.0"
        schema_version = 1
        usage_snapshot = @{
            lifetime_invoice_count = 0
            lifetime_ex_gst = "0.00"
        }
    } | ConvertTo-Json -Depth 4
    try {
        $resp = Invoke-RestMethod -Uri "https://api.frogswork.com/telemetry/heartbeat" `
            -Method POST -Body $body -ContentType "application/json" -TimeoutSec 15
        Write-Host "POST /telemetry/heartbeat -> $($resp | ConvertTo-Json -Compress)"
    } catch {
        Write-Warning "POST /telemetry/heartbeat failed: $_"
    }
}

Ensure-WranglerAuth

if ($DatabaseId) {
    Set-WranglerDatabaseId -Id $DatabaseId
} else {
    $DatabaseId = Get-OrCreate-DatabaseId
    Set-WranglerDatabaseId -Id $DatabaseId
}

Invoke-SchemaMigrate

if (-not $SkipDeploy) {
    Write-Host ""
    Write-Host "If secrets are not set yet, run (once each):"
    Write-Host "  cd account_api\worker"
    Write-Host "  npx wrangler secret put STRIPE_SECRET_KEY"
    Write-Host "  npx wrangler secret put STRIPE_WEBHOOK_SECRET"
    Write-Host "  npx wrangler secret put JWT_SECRET"
    Write-Host "  npx wrangler secret put ADMIN_PASSWORD"
    Write-Host ""
    Invoke-WorkerDeploy
    Test-ApiHealth
    Test-TelemetryHeartbeat
    Write-Host ""
    Write-Host "Admin dashboard: https://api.frogswork.com/admin (HTTP Basic, password = ADMIN_PASSWORD)"
}

Write-Host ""
Write-Host "D1 setup complete. database_id = $DatabaseId"
Write-Host "Commit account_api/worker/wrangler.toml if the database_id changed."
