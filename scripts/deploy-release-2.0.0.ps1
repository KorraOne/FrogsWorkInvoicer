# Build FrogsWork 2.0.0, upload to R2, set Worker release vars, deploy marketing.
# Prerequisite: D1 setup done (.\scripts\setup-d1-production.ps1), wrangler authenticated.
#
# Usage:
#   .\scripts\deploy-release-2.0.0.ps1
#   .\scripts\deploy-release-2.0.0.ps1 -SkipBuild -R2Bucket "your-bucket-name"

param(
    [string]$Version = "2.0.0",
    [string]$R2Bucket = "",
    [string]$ReleaseNotes = "Replaces usage-based billing with a simple monthly or annual subscription. Free trial: 20 invoices or `$20,000 ex GST before subscribe.",
    [switch]$SkipBuild,
    [switch]$SkipR2Upload,
    [switch]$SkipMarketingDeploy,
    [switch]$SkipWorkerDeploy
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$WorkerDir = Join-Path $Root "account_api\worker"
$MarketingDir = Join-Path $Root "marketing_site"
$WranglerToml = Join-Path $WorkerDir "wrangler.toml"
$ReleasesJson = Join-Path $MarketingDir "releases.json"
$SetupName = "FrogsWork-$Version-setup.exe"
$ZipName = "FrogsWork-$Version-win64.zip"
$SetupPath = Join-Path $Root "client_app\dist\$SetupName"
$ZipPath = Join-Path $Root "client_app\dist\$ZipName"

function Ensure-WranglerAuth {
    Push-Location $WorkerDir
    try {
        npx wrangler whoami | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Wrangler not authenticated. Run: npx wrangler login" }
    } finally {
        Pop-Location
    }
}

function Update-WorkerReleaseVars {
    param($Manifest)
    $raw = Get-Content $WranglerToml -Raw
    $version = $Manifest.version
    $url = $Manifest.update_zip_path
    $sha = $Manifest.sha256
    $notes = $Manifest.notes -replace '"', '\"'

    if ($raw -notmatch '\[vars\]') {
        $raw = $raw.TrimEnd() + "`n`n[vars]`n"
    }

    $replacements = @{
        'CLIENT_RELEASE_VERSION\s*=\s*"[^"]*"' = "CLIENT_RELEASE_VERSION = `"$version`""
        'CLIENT_RELEASE_URL\s*=\s*"[^"]*"' = "CLIENT_RELEASE_URL = `"$url`""
        'CLIENT_RELEASE_SHA256\s*=\s*"[^"]*"' = "CLIENT_RELEASE_SHA256 = `"$sha`""
        'CLIENT_RELEASE_NOTES\s*=\s*"[^"]*"' = "CLIENT_RELEASE_NOTES = `"$notes`""
    }

    foreach ($pattern in $replacements.Keys) {
        $replacement = $replacements[$pattern]
        if ($raw -match $pattern) {
            $raw = $raw -replace $pattern, $replacement
        } else {
            $raw = $raw.TrimEnd() + "`n$replacement"
        }
    }

    Set-Content -Path $WranglerToml -Value $raw -NoNewline
    Write-Host "Updated CLIENT_RELEASE_* in wrangler.toml"
}

function Upload-R2Object {
    param([string]$Bucket, [string]$Key, [string]$FilePath)
    if (-not (Test-Path $FilePath)) {
        throw "File not found: $FilePath"
    }
    Write-Host "Uploading $Key to R2 bucket $Bucket..."
    npx wrangler r2 object put "$Bucket/$Key" --file=$FilePath
    if ($LASTEXITCODE -ne 0) { throw "R2 upload failed for $Key" }
}

Ensure-WranglerAuth

if (-not $SkipBuild) {
    & (Join-Path $Root "scripts\package_client_release.ps1") -Version $Version -ReleaseNotes $ReleaseNotes
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not (Test-Path $ReleasesJson)) {
    throw "Missing $ReleasesJson - run package script first."
}
$manifest = Get-Content $ReleasesJson -Raw | ConvertFrom-Json

if (-not $SkipR2Upload) {
    if (-not $R2Bucket) {
        $R2Bucket = Read-Host "R2 bucket name (Cloudflare dashboard -> R2 -> your downloads bucket)"
    }
    if (-not $R2Bucket) { throw "R2 bucket name is required." }
    Push-Location $WorkerDir
    try {
        Upload-R2Object -Bucket $R2Bucket -Key $SetupName -FilePath $SetupPath
        Upload-R2Object -Bucket $R2Bucket -Key $ZipName -FilePath $ZipPath
    } finally {
        Pop-Location
    }
}

Update-WorkerReleaseVars -Manifest $manifest

if (-not $SkipWorkerDeploy) {
    Push-Location $WorkerDir
    try {
        npm run deploy
        if ($LASTEXITCODE -ne 0) { throw "Worker deploy failed." }
    } finally {
        Pop-Location
    }
    try {
        $latest = Invoke-RestMethod -Uri "https://api.frogswork.com/releases/latest" -TimeoutSec 15
        Write-Host "GET /releases/latest -> $($latest | ConvertTo-Json -Compress)"
    } catch {
        Write-Warning "/releases/latest check failed: $_"
    }
}

if (-not $SkipMarketingDeploy) {
    Push-Location $MarketingDir
    try {
        npx wrangler deploy
        if ($LASTEXITCODE -ne 0) { throw "Marketing deploy failed." }
    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "Release $Version deploy steps finished."
Write-Host "Verify: https://frogswork.com/download.html"
Write-Host "        https://downloads.frogswork.com/$SetupName"
