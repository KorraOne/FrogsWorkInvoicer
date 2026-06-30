# Build FrogsWork Inno Setup installer from PyInstaller onedir output.

param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [string]$AppSource = "",
    [string]$InnoSetupPath = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$IssFile = Join-Path $Root "installer\FrogsWork.iss"
$DistDir = Join-Path $Root "client_app\dist\FrogsWork"
$OutDir = Join-Path $Root "client_app\dist"
$SetupName = "FrogsWork-$Version-setup.exe"
$SetupPath = Join-Path $OutDir $SetupName

if (-not $AppSource) {
    $AppSource = $DistDir
}

if (-not (Test-Path (Join-Path $AppSource "FrogsWork.exe"))) {
    throw "PyInstaller output not found: $AppSource\FrogsWork.exe (run build_client.ps1 first)"
}

if (-not $InnoSetupPath) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $InnoSetupPath = $candidate
            break
        }
    }
}

if (-not $InnoSetupPath -or -not (Test-Path $InnoSetupPath)) {
    throw "Inno Setup 6 not found. Install from https://jrsoftware.org/isdl.php or pass -InnoSetupPath"
}

if (Test-Path $SetupPath) {
    Remove-Item -Force $SetupPath
}

if ($AppSource -and (Resolve-Path $AppSource).Path -ne (Resolve-Path $DistDir).Path) {
    & $InnoSetupPath "/DAppVersion=$Version" "/DAppSource=$AppSource" $IssFile
} else {
    & $InnoSetupPath "/DAppVersion=$Version" $IssFile
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path $SetupPath)) {
    throw "Installer build failed: $SetupPath was not created"
}

Write-Host "Installer: $SetupPath"
