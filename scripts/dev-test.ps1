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

$Root = Split-Path $PSScriptRoot -Parent

$BillingDir = Join-Path $Root "billing_server"

$AppDir = Join-Path $Root "client_app"

$DbPath = Join-Path $BillingDir "billing.db"

$AppDataPath = Join-Path $env:APPDATA "FrogsWork"

$BuiltExe = Join-Path $AppDir "dist\FrogsWork\FrogsWork.exe"



function Confirm-Destructive {

    param([string]$Message)

    if ($Force) {

        return

    }

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



function Start-BillingServer {

    $envFile = Join-Path $BillingDir ".env"
    $envExample = Join-Path $BillingDir ".env.example"
    if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
        Copy-Item $envExample $envFile
        Write-Host "Created billing_server/.env from .env.example"
    }

    Write-Host "Starting billing server in a new window..."

    $cmd = @"

Set-Location '$BillingDir'

`$env:DATABASE_URL = '$DbPath'

python app.py

"@

    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd

}



function Start-DesktopApp {

    Stop-AppOnPort -Port 5000

    Start-Sleep -Seconds 1

    $pythonw = (Get-Command python -ErrorAction Stop).Source -replace "python.exe", "pythonw.exe"
    if (-not (Test-Path $pythonw)) {
        $pythonw = (Get-Command python -ErrorAction Stop).Source
    }

    if ($DevBrowser) {
        Write-Host "Starting app in dev browser mode (PowerShell + python)..."
        $cmd = @"
Set-Location '$AppDir'
`$env:FROGSWORK_DEV_BROWSER = '1'
`$env:BILLING_SERVER_URL = 'http://127.0.0.1:8080'
python app.py
"@
        Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd
        return
    }

    Write-Host "Starting FrogsWork desktop window (no console)..."
    Write-Host "Tip: for the full product feel, build with .\build_client.ps1 and run the .exe"

    $envBlock = "`$env:BILLING_SERVER_URL = 'http://127.0.0.1:8080'"
    $cmd = @"
Set-Location '$AppDir'
$envBlock
& '$pythonw' app.py
"@
    Start-Process powershell -ArgumentList "-WindowStyle", "Hidden", "-Command", $cmd

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

        Start-BillingServer

        Start-Sleep -Seconds 2

    }



    Write-Host "Launching built exe: $BuiltExe"

    Start-Process $BuiltExe

}



function Invoke-SeedDevData {

    $python = (Get-Command python -ErrorAction Stop).Source

    if ($ResetSeed) {

        Confirm-Destructive "Replace customers/invoices and re-apply seed settings in $AppDataPath?"

    } else {

        Confirm-Destructive "Merge dev seed data into $AppDataPath (skip existing names/invoice numbers)?"

    }

    $args = @("seed_dev_data.py")

    if ($ResetSeed) {

        $args += "--reset"

    }

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

    foreach ($path in @($AppDataPath)) {
        if (Test-Path $path) {
            Remove-Item -Recurse -Force $path
            Write-Host "Removed $path"
        } else {
            Write-Host "AppData folder not found (already clear): $path"
        }
    }

}



function Clear-BillingDb {

    Confirm-Destructive "Delete billing database at $DbPath?"

    $removed = $false

    foreach ($path in @($DbPath, (Join-Path $BillingDir "test_billing.db"))) {

        if (Test-Path $path) {

            Remove-Item -Force $path

            Write-Host "Removed $path"

            $removed = $true

        }

    }

    if (-not $removed) {

        Write-Host "Database not found (already clear): $DbPath"

    } else {

        Write-Host "Restart the billing server so the schema is re-created on startup."

    }

}



function Show-OfflineTestChecklist {

    Write-Host ""

    Write-Host "=== Offline test checklist (built exe, no billing server) ===" -ForegroundColor Cyan

    Write-Host "1. Complete welcome wizard"

    Write-Host "2. Add a customer and create an invoice under `$2,000 ex-GST"

    Write-Host "3. Confirm PDF generates and no dev error strings appear"

    Write-Host "4. Try Create account — expect friendly offline message"

    Write-Host "5. Close the app window — process should exit (no orphan on port 5000)"

    Write-Host ""

}



function Show-OnlineTestChecklist {

    Write-Host ""

    Write-Host "=== Online test checklist (billing server + built exe) ===" -ForegroundColor Cyan

    Write-Host "1. Billing server running on http://127.0.0.1:8080"

    Write-Host "2. Create account through styled signup flow"

    Write-Host "3. Sign in; Settings -> Your account shows Account services: Available"

    Write-Host "4. Generate invoice; usage syncs when over free tier or cap enabled"

    Write-Host ""

}



switch ($Action) {

    "StartServer" { Start-BillingServer }

    "StartApp" { Start-DesktopApp }

    "StartAll" {

        Start-BillingServer

        Start-Sleep -Seconds 1

        Start-DesktopApp

    }

    "ClearAppData" { Clear-AppDataFolder }

    "ClearDb" { Clear-BillingDb }

    "ResetAll" {

        Clear-AppDataFolder

        Clear-BillingDb

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

