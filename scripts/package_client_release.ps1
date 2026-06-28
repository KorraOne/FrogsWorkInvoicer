# Package FrogsWork for distribution — zip, marketing manifest, billing server env hints.

param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [switch]$SkipBuild,
    [string]$BillingUrl = "https://api.frogswork.com",
    [string]$MarketingSiteUrl = "https://frogswork.com",
    [string]$DownloadHost = "https://downloads.frogswork.com",
    [string]$ReleaseNotes = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$DistDir = Join-Path $Root "client_app\dist\FrogsWork"
$OutDir = Join-Path $Root "client_app\dist"
$MarketingDir = Join-Path $Root "marketing_site"
$DownloadsDir = Join-Path $MarketingDir "downloads"
$ZipName = "FrogsWork-$Version-win64.zip"
$ZipPath = Join-Path $OutDir $ZipName
$MarketingZipPath = Join-Path $DownloadsDir $ZipName
$DownloadUrl = "$($DownloadHost.TrimEnd('/'))/$ZipName"

if (-not $SkipBuild) {
    $buildArgs = @("-Clean")
    if ($BillingUrl) {
        $buildArgs += @("-BillingUrl", $BillingUrl)
    }
    & (Join-Path $Root "build_client.ps1") @buildArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not (Test-Path (Join-Path $DistDir "FrogsWork.exe"))) {
    throw "Build output not found: $DistDir\FrogsWork.exe"
}

New-Item -ItemType Directory -Force -Path $DownloadsDir | Out-Null

if (Test-Path $ZipPath) {
    Remove-Item -Force $ZipPath
}

Compress-Archive -Path (Join-Path $DistDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal
Copy-Item -Force $ZipPath $MarketingZipPath

$hash = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToLower()
$publishedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")

$manifest = @{
    version       = $Version
    download_path = $DownloadUrl
    sha256        = $hash
    notes         = $ReleaseNotes
    published_at  = $publishedAt
} | ConvertTo-Json -Depth 3

Set-Content -Path (Join-Path $MarketingDir "releases.json") -Value $manifest -Encoding utf8

Write-Host ""
Write-Host "Release package: $ZipPath"
Write-Host "Local copy:      $MarketingZipPath (upload to R2; do not commit large zips)"
Write-Host "Public URL:      $DownloadUrl"
Write-Host "SHA256: $hash"
Write-Host ""
Write-Host "1. Upload zip to R2 bucket (downloads.frogswork.com)"
Write-Host "2. Push marketing_site/releases.json to Cloudflare Pages"
Write-Host "3. Add to /etc/frogswork/billing.env on Pi:"
Write-Host "CLIENT_RELEASE_VERSION=$Version"
Write-Host "CLIENT_RELEASE_URL=$DownloadUrl"
Write-Host "CLIENT_RELEASE_SHA256=$hash"
if ($ReleaseNotes) {
    Write-Host "CLIENT_RELEASE_NOTES=$ReleaseNotes"
} else {
    Write-Host "CLIENT_RELEASE_NOTES=Describe this release."
}
Write-Host ""
Write-Host "Confirm client_app/app_config.py APP_VERSION = `"$Version`""
