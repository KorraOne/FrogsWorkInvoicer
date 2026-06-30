# Clear local FrogsWork dev state and optionally seed sample data.
#
# Usage:
#   .\scripts\reset-dev.ps1 -Force
#   .\scripts\reset-dev.ps1 -SeedOnly -Force
#   .\scripts\reset-dev.ps1 -Force -Seed -ResetSeed

param(
    [switch]$SeedOnly,
    [switch]$Seed,
    [switch]$ResetSeed,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

. "$PSScriptRoot\_dev-env.ps1"

$AppDataPath = Join-Path $env:APPDATA "FrogsWork"
$ApiDbPath = Join-Path $ApiDir "account_api.db"

function Confirm-Destructive {
    param([string]$Message)
    if ($Force) { return }
    $answer = Read-Host "$Message Type YES to confirm"
    if ($answer -ne "YES") {
        Write-Host "Cancelled."
        exit 0
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

$doClear = -not $SeedOnly
$doSeed = $Seed -or $SeedOnly

if ($doClear) {
    Clear-AppDataFolder
    Clear-AccountApiDb
}

if ($doSeed) {
    Invoke-SeedDevData
}

if (-not $doClear -and -not $doSeed) {
    Write-Host "Nothing to do. Examples:"
    Write-Host "  .\scripts\reset-dev.ps1 -Force"
    Write-Host "  .\scripts\reset-dev.ps1 -Force -Seed -ResetSeed"
    exit 1
}
