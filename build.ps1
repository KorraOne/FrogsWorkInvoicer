# Build InvoiceApp with an isolated venv and a slim PyInstaller bundle.
#
# Usage:
#   .\build.ps1              Fast startup (onedir folder in invoice_app\dist\InvoiceApp\)
#   .\build.ps1 -OneFile     Single exe (slower cold start, easier to copy)
#   .\build.ps1 -Clean       Wipe build cache before building
#   .\build.ps1 -SkipVenv    Use current Python instead of .build-venv

param(
    [switch]$OneFile,
    [switch]$Clean,
    [switch]$SkipVenv
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$AppDir = Join-Path $Root "invoice_app"
$VenvDir = Join-Path $Root ".build-venv"
$Requirements = Join-Path $Root "requirements.txt"
$DistOnedir = Join-Path $AppDir "dist\InvoiceApp"
$DistOneFile = Join-Path $AppDir "dist\InvoiceApp.exe"

Set-Location $AppDir

# Stop a running copy so PyInstaller can overwrite outputs
Get-Process -Name "InvoiceApp" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500

if (-not $SkipVenv) {
    if (-not (Test-Path $VenvDir)) {
        Write-Host "Creating build venv (.build-venv) with only app dependencies..."
        python -m venv $VenvDir
    }
    $python = Join-Path $VenvDir "Scripts\python.exe"
    $pyinstaller = Join-Path $VenvDir "Scripts\pyinstaller.exe"
    Write-Host "Installing/updating dependencies in build venv..."
    & $python -m pip install -q -r $Requirements
} else {
    $pyinstaller = "pyinstaller"
    if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
        throw "pyinstaller not found. Run without -SkipVenv or: pip install -r requirements.txt"
    }
}

if ($Clean) {
    Write-Host "Cleaning build artifacts..."
    Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
}

if ($OneFile) {
    $env:INVOICEAPP_ONEFILE = "1"
    Write-Host "Building ONE-FILE exe (slower startup, single file)..."
} else {
    $env:INVOICEAPP_ONEFILE = "0"
    Write-Host "Building ONEDIR bundle (faster startup)..."
}

$buildStart = Get-Date
& $pyinstaller InvoiceApp.spec --noconfirm --log-level WARN
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$elapsed = (Get-Date) - $buildStart
Write-Host ""
Write-Host ("Build finished in {0:N1}s" -f $elapsed.TotalSeconds) -ForegroundColor Green

if ($OneFile) {
    if (Test-Path $DistOneFile) {
        $sizeMb = [math]::Round((Get-Item $DistOneFile).Length / 1MB, 1)
        Write-Host "Output: $DistOneFile ($sizeMb MB)"
    }
} else {
  if (Test-Path $DistOnedir) {
        $sizeMb = [math]::Round(((Get-ChildItem $DistOnedir -Recurse | Measure-Object Length -Sum).Sum / 1MB), 1)
        Write-Host "Output: $DistOnedir ($sizeMb MB total)"
        Write-Host "Run:     $DistOnedir\InvoiceApp.exe"
    }
}
