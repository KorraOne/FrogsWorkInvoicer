# Pre-deploy verification for centralized web account flow.
# Prerequisite: API on :8787 (start-pwa-dev.ps1 or start-dev.ps1).
#
# Usage:
#   .\scripts\verify-local-account-setup.ps1
#   .\scripts\verify-local-account-setup.ps1 -StartMarketing

param(
    [switch]$StartMarketing,
    [int]$MarketingPort = 8080
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$ApiUrl = if ($env:FROGSWORK_ACCOUNT_API_URL) { $env:FROGSWORK_ACCOUNT_API_URL } else { "http://127.0.0.1:8787" }
$MarketingUrl = "http://127.0.0.1:$MarketingPort"
$MarketingDir = Join-Path $Root "marketing_site"
$python = if (Test-Path (Join-Path $Root ".client-venv\Scripts\python.exe")) {
    Join-Path $Root ".client-venv\Scripts\python.exe"
} else {
    (Get-Command python).Source
}

$failures = @()
$passed = 0

function Pass([string]$msg) {
    Write-Host "[OK] $msg" -ForegroundColor Green
    $script:passed++
}

function Fail([string]$msg) {
    Write-Host "[FAIL] $msg" -ForegroundColor Red
    $script:failures += $msg
}

function Test-Http {
    param([string]$Url, [string]$Label, [hashtable]$Headers = @{})
    try {
        $resp = Invoke-WebRequest -Uri $Url -Headers $Headers -UseBasicParsing -TimeoutSec 10
        if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400) {
            Pass "$Label ($Url)"
            return $resp
        }
        Fail "$Label returned $($resp.StatusCode)"
    } catch {
        Fail "$Label - $($_.Exception.Message)"
    }
    return $null
}

$marketingProc = $null
if ($StartMarketing) {
    Write-Host "Starting marketing site on $MarketingUrl ..."
    $marketingProc = Start-Process -FilePath $python -ArgumentList @("-m", "http.server", $MarketingPort) -WorkingDirectory $MarketingDir -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "=== FrogsWork account flow verification ===" -ForegroundColor Cyan
Write-Host "API:       $ApiUrl"
Write-Host "Marketing: $MarketingUrl"
Write-Host ""

# API health
Test-Http "$ApiUrl/health" "API health" | Out-Null

# CORS preflight from marketing origin
try {
    $cors = Invoke-WebRequest -Uri "$ApiUrl/health" -Method OPTIONS -Headers @{
        Origin = $MarketingUrl
        "Access-Control-Request-Method" = "GET"
    } -UseBasicParsing -TimeoutSec 10
    $acao = $cors.Headers["Access-Control-Allow-Origin"]
    if ($acao -eq $MarketingUrl) {
        Pass "CORS allows marketing origin ($MarketingUrl)"
    } else {
        Fail "CORS missing for marketing origin (got: $acao)"
    }
} catch {
    Fail "CORS preflight - $($_.Exception.Message)"
}

# CORS from PWA origin
try {
    $cors = Invoke-WebRequest -Uri "$ApiUrl/health" -Method OPTIONS -Headers @{
        Origin = "http://127.0.0.1:8090"
        "Access-Control-Request-Method" = "POST"
    } -UseBasicParsing -TimeoutSec 10
    if ($cors.Headers["Access-Control-Allow-Origin"] -eq "http://127.0.0.1:8090") {
        Pass "CORS allows PWA origin (127.0.0.1:8090)"
    } else {
        Fail "CORS missing for PWA origin"
    }
} catch {
    Fail "PWA CORS preflight - $($_.Exception.Message)"
}

# Marketing account pages
foreach ($page in @(
    "/account/signup.html",
    "/account/subscribe.html",
    "/account/login.html",
    "/account/return.html",
    "/account/create.html",
    "/account/success.html"
)) {
    $resp = Test-Http "$MarketingUrl$page" "Marketing page $page"
    if ($resp -and $page -eq "/account/subscribe.html" -and $resp.Content -notmatch "tier-plans") {
        Fail "subscribe.html missing tier plan markup"
    }
}

# Signup API shape (no Stripe required)
try {
    $testEmail = "verify-{0}@example.com" -f ([guid]::NewGuid().ToString("N").Substring(0, 8))
    $signupBody = @{ email = $testEmail; password = "TestPass123!" } | ConvertTo-Json
    $signupResp = Invoke-RestMethod -Uri "$ApiUrl/auth/signup" -Method POST -Body $signupBody -ContentType "application/json" -TimeoutSec 10
    if ($signupResp.signup_token -and $signupResp.account_status -eq "pending_payment") {
        Pass "POST /auth/signup returns signup_token"
    } else {
        Fail "POST /auth/signup unexpected response"
    }
} catch {
    Fail "POST /auth/signup - $($_.Exception.Message)"
}

# Marketing JS modules
foreach ($js in @("config.js", "api.js", "signup.js", "subscribe.js", "login.js", "return.js")) {
    Test-Http "$MarketingUrl/js/account/$js" "Marketing JS $js" | Out-Null
}

# Desktop route checks (Flask test client)
$desktopTest = Join-Path $PSScriptRoot "verify_desktop_account_routes.py"
& $python $desktopTest
if ($LASTEXITCODE -eq 0) {
    Pass "Desktop Flask account routes redirect / callback"
} else {
    Fail "Desktop Flask account route checks failed (see output above)"
}

# Unit tests
Push-Location (Join-Path $Root "client_app")
try {
    & $python -m pytest tests/ -q --tb=no 2>&1 | Tee-Object -Variable pytestOut
    if ($LASTEXITCODE -eq 0) {
        Pass "Desktop unit tests (pytest)"
    } else {
        Fail "Desktop unit tests failed"
        $pytestOut | Select-Object -Last 15 | ForEach-Object { Write-Host $_ }
    }
} finally {
    Pop-Location
}

# PWA domain tests if node available
$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
    Push-Location (Join-Path $Root "client_web")
    try {
        & node --test js/domain/domain.test.js 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Pass "PWA domain unit tests (node)"
        } else {
            Fail "PWA domain unit tests failed"
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "[SKIP] Node not found - PWA domain tests" -ForegroundColor Yellow
}

if ($marketingProc) {
    Stop-Process -Id $marketingProc.Id -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Passed: $passed"
Write-Host "Failed: $($failures.Count)"
if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "Fix failures before deploying to production." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Automated checks passed." -ForegroundColor Green
Write-Host ""
Write-Host "Manual E2E (still required before prod):" -ForegroundColor Yellow
Write-Host "  1. Terminal A: .\scripts\start-pwa-dev.ps1"
Write-Host "  2. Terminal B: cd marketing_site; python -m http.server $MarketingPort"
Write-Host "  3. Set STRIPE_PRICE_* in account_api/dev/.dev.vars (run setup_stripe_prices.py)"
Write-Host "  4. Terminal C: .\scripts\start-dev.ps1  (desktop on :5000)"
Write-Host "  5. Signup: $MarketingUrl/account/signup.html -> choose plan -> Stripe test card 4242..."
Write-Host "  6. Desktop Sign in -> web login -> should return to http://127.0.0.1:5000/account/auth/callback"
Write-Host "  7. PWA: http://127.0.0.1:8090 -> Sign in (Cloud) or Upgrade to Cloud"
exit 0
