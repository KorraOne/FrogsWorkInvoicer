# Dev helpers for FrogsWork testing.
#
# Usage:
#   .\scripts\dev-test.ps1 -Action StartAll
#   .\scripts\dev-test.ps1 -Action StartAll -DevBrowser
#   .\scripts\dev-test.ps1 -Action TestOffline -Force
#   .\scripts\dev-test.ps1 -Action TestOnline -Force
#   .\scripts\dev-test.ps1 -Action SeedDevData
#   .\scripts\dev-test.ps1 -Action SeedDevData -ResetSeed -Force
#   .\scripts\dev-test.ps1 -Action ResetAll -Force; .\scripts\dev-test.ps1 -Action SeedDevData -Force

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "StartServer", "StartApp", "StartAll",
        "ClearAppData", "ClearDb", "ResetAll",
        "SeedDevData",
        "TestOffline", "TestOnline"
    )]
    [string]$Action,

    [switch]$Force,
    [switch]$DevBrowser,
    [switch]$ResetSeed
)

$ErrorActionPreference = "Stop"

. "$PSScriptRoot\_dev-env.ps1"

$AppDataPath = Join-Path $env:APPDATA "FrogsWork"
$ApiDbPath = Join-Path $ApiDir "account_api.db"
$BuiltExe = Join-Path $AppDir "dist\FrogsWork\FrogsWork.exe"

function Confirm-Destructive {
    param([string]$Message)
    if ($Force) { return }
    $answer = Read-Host "$Message Type YES to confirm"
    if ($answer -ne "YES") {
        Write-Host "Cancelled."
        exit 0
    }
}

function Stop-AppOnPort {
    param([int]$Port)
    Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        ForEach-Object {
            $procId = $_.OwningProcess
            if ($procId -and $procId -ne 0) {
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                Write-Host "Stopped process $procId on port $Port"
            }
        }
}

function Start-AccountApi {
    Write-Host "Starting account API in a new window..."
    Start-FrogsWorkApiTerminal
}

function Start-DesktopApp {
    Stop-AppOnPort -Port 5000
    Start-Sleep -Seconds 1
    Write-Host "Starting FrogsWork app in a new window..."
    Start-FrogsWorkAppTerminal -DevBrowser:$DevBrowser
}

function Start-BuiltApp {
    param([switch]$WithServer)

    if (-not (Test-Path $BuiltExe)) {
        Write-Host "Built exe not found. Run .\build_client.ps1 first."
        exit 1
    }

    Stop-AppOnPort -Port 5000
    Start-Sleep -Seconds 1

    if ($WithServer) {
        Start-AccountApi
        Start-Sleep -Seconds 2
    }

    Write-Host "Launching built exe: $BuiltExe"
    Start-Process $BuiltExe
}

function Invoke-SeedDevData {
    $python = Get-FrogsWorkPython
    if ($ResetSeed) {
        Confirm-Destructive "Replace customers/invoices and re-apply seed settings in $AppDataPath?"
    } else {
        Confirm-Destructive "Merge dev seed data into $AppDataPath (skip existing names/invoice numbers)?"
    }
    $args = @("seed_dev_data.py")
    if ($ResetSeed) { $args += "--reset" }
    Push-Location $AppDir
    try {
        & $python @args
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
}

function Clear-AppDataFolder {
    Confirm-Destructive "Delete all FrogsWork data in $AppDataPath?"
    if (Test-Path $AppDataPath) {
        Remove-Item -Recurse -Force $AppDataPath
        Write-Host "Removed $AppDataPath"
    } else {
        Write-Host "AppData folder not found (already clear): $AppDataPath"
    }
}

function Clear-AccountApiDb {
    Confirm-Destructive "Delete local account API database at $ApiDbPath?"
    if (Test-Path $ApiDbPath) {
        Remove-Item -Force $ApiDbPath
        Write-Host "Removed $ApiDbPath"
        Write-Host "Restart the account API so the schema is re-created on startup."
    } else {
        Write-Host "Database not found (already clear): $ApiDbPath"
    }
}

function Show-OfflineTestChecklist {
    Write-Host ""
    Write-Host "=== Offline test checklist (built exe, no account API) ===" -ForegroundColor Cyan
    Write-Host "1. Complete welcome wizard"
    Write-Host "2. Add a customer and create an invoice under trial limits"
    Write-Host "3. Confirm PDF generates"
    Write-Host "4. Try Create account — expect friendly offline message"
    Write-Host "5. Close the app window — process should exit (no orphan on port 5000)"
    Write-Host ""
}

function Show-OnlineTestChecklist {
    Write-Host ""
    Write-Host "=== Online test checklist (account API + built exe) ===" -ForegroundColor Cyan
    Write-Host "1. Account API running on $(Get-FrogsWorkAccountApiUrl)"
    Write-Host "2. Create account and subscribe via Stripe test flow"
    Write-Host "3. Sign in; Settings -> Your account shows subscription status"
    Write-Host "4. Generate invoice while subscribed"
    Write-Host ""
}

switch ($Action) {
    "StartServer" { Start-AccountApi }
    "StartApp" { Start-DesktopApp }
    "StartAll" {
        Start-AccountApi
        Start-Sleep -Seconds 2
        Start-DesktopApp
    }
    "ClearAppData" { Clear-AppDataFolder }
    "ClearDb" { Clear-AccountApiDb }
    "ResetAll" {
        Clear-AppDataFolder
        Clear-AccountApiDb
    }
    "SeedDevData" { Invoke-SeedDevData }
    "TestOffline" {
        Show-OfflineTestChecklist
        Start-BuiltApp -WithServer:$false
    }
    "TestOnline" {
        Show-OnlineTestChecklist
        Start-BuiltApp -WithServer:$true
    }
}
