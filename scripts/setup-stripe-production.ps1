# Configure Stripe for production: API Worker secrets + Payment Link redirects.
# Prerequisite: client_app\production.env with payment link URLs (+ STRIPE_SECRET_KEY for redirects).
#
# Usage:
#   .\scripts\setup-stripe-production.ps1
#   .\scripts\setup-stripe-production.ps1 -SkipPaymentLinkRedirects

param(
    [switch]$SkipPaymentLinkRedirects,
    [switch]$SkipWorkerSecrets
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot "_production-env.ps1")
. (Join-Path $PSScriptRoot "_dev-env.ps1")

$productionEnv = Import-ProductionEnv
$WorkerDir = Join-Path $Root "account_api\worker"

function Set-WorkerSecret {
    param([string]$Name, [string]$Value)
    if (-not $Value) { throw "Missing value for Worker secret $Name" }
    Push-Location $WorkerDir
    try {
        $Value | npx wrangler secret put $Name
        if ($LASTEXITCODE -ne 0) { throw "wrangler secret put $Name failed." }
    } finally {
        Pop-Location
    }
    Write-Host "Set Worker secret: $Name"
}

function New-JwtSecret {
    $bytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return [Convert]::ToBase64String($bytes)
}

function Ensure-WranglerAuth {
    Push-Location $WorkerDir
    try {
        npx wrangler whoami | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Wrangler not authenticated. Run: npx wrangler login" }
    } finally {
        Pop-Location
    }
}

Ensure-WranglerAuth

if (-not $SkipWorkerSecrets) {
    $stripeKey = $productionEnv["STRIPE_SECRET_KEY"]
    if (-not $stripeKey) {
        throw "STRIPE_SECRET_KEY required in client_app\production.env"
    }
    $jwtSecret = $productionEnv["JWT_SECRET"]
    if (-not $jwtSecret) {
        $jwtSecret = New-JwtSecret
        Write-Host "Generated JWT_SECRET (add JWT_SECRET to production.env to reuse across runs)."
    }
    $webhookSecret = $productionEnv["STRIPE_WEBHOOK_SECRET"]
    if (-not $webhookSecret) {
        Write-Host "STRIPE_WEBHOOK_SECRET not in production.env - using placeholder (configure Stripe webhooks later)."
        $webhookSecret = "whsec_placeholder_configure_in_stripe_dashboard"
    }
    Set-WorkerSecret -Name "STRIPE_SECRET_KEY" -Value $stripeKey
    Set-WorkerSecret -Name "JWT_SECRET" -Value $jwtSecret
    Set-WorkerSecret -Name "STRIPE_WEBHOOK_SECRET" -Value $webhookSecret
    Push-Location $WorkerDir
    try {
        npm run deploy
        if ($LASTEXITCODE -ne 0) { throw "Worker deploy failed." }
    } finally {
        Pop-Location
    }
    Write-Host "Worker secrets set and deployed."
}

if (-not $SkipPaymentLinkRedirects) {
    $monthly = $productionEnv["STRIPE_PAYMENT_LINK_MONTHLY"]
    $annual = $productionEnv["STRIPE_PAYMENT_LINK_ANNUAL"]
    $stripeKey = $productionEnv["STRIPE_SECRET_KEY"]
    if (-not $monthly -or -not $annual) {
        throw "STRIPE_PAYMENT_LINK_MONTHLY and STRIPE_PAYMENT_LINK_ANNUAL required in client_app\production.env"
    }
    if (-not $stripeKey) {
        throw "STRIPE_SECRET_KEY required in client_app\production.env to configure Payment Link redirects."
    }
    $env:STRIPE_PAYMENT_LINK_MONTHLY = $monthly
    $env:STRIPE_PAYMENT_LINK_ANNUAL = $annual
    $env:STRIPE_SECRET_KEY = $stripeKey
    $env:STRIPE_CHECKOUT_RETURN_URL = "https://frogswork.com/account/return.html?session_id={CHECKOUT_SESSION_ID}"
    $syncConfig = Join-Path $Root "scripts\sync-marketing-account-config.ps1"
    if (Test-Path $syncConfig) {
        & $syncConfig
    }
    $python = Ensure-FrogsWorkApiDeps
    Push-Location (Join-Path $Root "account_api\dev")
    try {
        & $python configure_payment_links.py
        if ($LASTEXITCODE -ne 0) { throw "Payment link redirect configuration failed." }
    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "Stripe production setup complete."
Write-Host "Create tier prices: python account_api\dev\setup_stripe_prices.py --grandfather-existing"
Write-Host "Add STRIPE_PRICE_* to production.env and wrangler.toml [vars], then redeploy worker."
