# Package FrogsWork for distribution — installer, update zip, marketing manifest.

param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [switch]$SkipBuild,
    [string]$BillingUrl = "https://api.frogswork.com",
    [string]$MarketingSiteUrl = "https://frogswork.com",
    [string]$DownloadHost = "https://downloads.frogswork.com",
    [string]$ReleaseNotes = "",
    [string]$InnoSetupPath = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$DistDir = Join-Path $Root "client_app\dist\FrogsWork"
$OutDir = Join-Path $Root "client_app\dist"
$MarketingDir = Join-Path $Root "marketing_site"
$DownloadsDir = Join-Path $MarketingDir "downloads"
$ZipName = "FrogsWork-$Version-win64.zip"
$SetupName = "FrogsWork-$Version-setup.exe"
$ZipPath = Join-Path $OutDir $ZipName
$SetupPath = Join-Path $OutDir $SetupName
$MarketingZipPath = Join-Path $DownloadsDir $ZipName
$MarketingSetupPath = Join-Path $DownloadsDir $SetupName
$SetupDownloadUrl = "$($DownloadHost.TrimEnd('/'))/$SetupName"
$ZipDownloadUrl = "$($DownloadHost.TrimEnd('/'))/$ZipName"

if (-not $SkipBuild) {
    $buildClient = Join-Path $Root "build_client.ps1"
    if ($BillingUrl) {
        & $buildClient -Clean -BillingUrl $BillingUrl
    } else {
        & $buildClient -Clean
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not (Test-Path (Join-Path $DistDir "FrogsWork.exe"))) {
    throw "Build output not found: $DistDir\FrogsWork.exe"
}

New-Item -ItemType Directory -Force -Path $DownloadsDir | Out-Null

if (Test-Path $ZipPath) {
    Remove-Item -Force $ZipPath
}

# Zip the FrogsWork folder so in-app updates extract to FrogsWork\FrogsWork.exe.
$StageDir = Join-Path $OutDir "_zip_stage"
$StageRoot = Join-Path $StageDir "FrogsWork"
if (Test-Path $StageDir) {
    Remove-Item -Recurse -Force $StageDir
}
New-Item -ItemType Directory -Force -Path $StageRoot | Out-Null
Copy-Item -Recurse -Force (Join-Path $DistDir "*") $StageRoot
Compress-Archive -Path $StageRoot -DestinationPath $ZipPath -CompressionLevel Optimal
Remove-Item -Recurse -Force $StageDir
Copy-Item -Force $ZipPath $MarketingZipPath

$zipHash = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToLower()

$installerParams = @{ Version = $Version }
if ($InnoSetupPath) {
    $installerParams.InnoSetupPath = $InnoSetupPath
}
& (Join-Path $Root "scripts\build_installer.ps1") @installerParams
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Copy-Item -Force $SetupPath $MarketingSetupPath
$setupHash = (Get-FileHash -Path $SetupPath -Algorithm SHA256).Hash.ToLower()
$publishedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")

$manifest = @{
    version            = $Version
    download_path      = $SetupDownloadUrl
    setup_sha256       = $setupHash
    update_zip_path    = $ZipDownloadUrl
    sha256             = $zipHash
    notes              = $ReleaseNotes
    published_at       = $publishedAt
} | ConvertTo-Json -Depth 3

Set-Content -Path (Join-Path $MarketingDir "releases.json") -Value $manifest -Encoding utf8

Write-Host ""
Write-Host "Setup (marketing):  $SetupPath"
Write-Host "Zip (in-app update): $ZipPath"
Write-Host "Local copies:       $MarketingSetupPath"
Write-Host "                    $MarketingZipPath"
Write-Host ""
Write-Host "Public setup URL:   $SetupDownloadUrl"
Write-Host "Setup SHA256:       $setupHash"
Write-Host "Update zip URL:     $ZipDownloadUrl"
Write-Host "Update zip SHA256:  $zipHash"
Write-Host ""
Write-Host "1. Upload setup.exe and zip to R2 (downloads.frogswork.com)"
Write-Host "2. Push marketing_site/releases.json to Cloudflare Pages"
Write-Host "3. Add to /etc/frogswork/billing.env on Pi (in-app updates use the zip):"
Write-Host "CLIENT_RELEASE_VERSION=$Version"
Write-Host "CLIENT_RELEASE_URL=$ZipDownloadUrl"
Write-Host "CLIENT_RELEASE_SHA256=$zipHash"
if ($ReleaseNotes) {
    Write-Host "CLIENT_RELEASE_NOTES=$ReleaseNotes"
} else {
    Write-Host "CLIENT_RELEASE_NOTES=Describe this release."
}
Write-Host ""
Write-Host "Confirm client_app/app_config.py APP_VERSION = `"$Version`""
