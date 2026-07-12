# Write Stripe plan config from production.env into marketing_site/js/account/config.js

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot "_production-env.ps1")

$vars = Import-ProductionEnv
$monthly = $vars["STRIPE_PAYMENT_LINK_MONTHLY"]
$annual = $vars["STRIPE_PAYMENT_LINK_ANNUAL"]

function Get-PlanDisplay([string]$key, [string]$default) {
    if ($vars.ContainsKey($key) -and $vars[$key]) { return $vars[$key] }
    return $default
}

$configPath = Join-Path $Root "marketing_site\js\account\config.js"
$content = Get-Content $configPath -Raw -Encoding UTF8

if ($monthly -and $annual) {
    $content = $content -replace '(?m)^export const PAYMENT_LINKS = \{[^}]*\};', @"
export const PAYMENT_LINKS = {
  monthly: "$monthly",
  annual: "$annual",
};
"@
}

$localMonthly = Get-PlanDisplay "PLAN_LOCAL_MONTHLY_DISPLAY" '$9.99/mo'
$localAnnual = Get-PlanDisplay "PLAN_LOCAL_ANNUAL_DISPLAY" '$99/yr'
$cloudMonthly = Get-PlanDisplay "PLAN_CLOUD_MONTHLY_DISPLAY" '$14.99/mo'
$cloudAnnual = Get-PlanDisplay "PLAN_CLOUD_ANNUAL_DISPLAY" '$149/yr'

$plansBlock = @"
export const PLANS = {
  local: {
    monthly: { display: "$localMonthly", interval: "month" },
    annual: { display: "$localAnnual", interval: "year" },
  },
  cloud: {
    monthly: { display: "$cloudMonthly", interval: "month" },
    annual: { display: "$cloudAnnual", interval: "year" },
  },
};
"@

if ($content -match '(?m)^export const PLANS = \{') {
    $content = $content -replace '(?ms)^export const PLANS = \{.*?\n\};', $plansBlock
} else {
    $content = $content -replace '(export const PAYMENT_LINKS = \{[\s\S]*?\};)', "`$1`n`n$plansBlock"
}

Set-Content -Path $configPath -Value $content -NoNewline -Encoding UTF8
Write-Host "Updated PAYMENT_LINKS / PLANS in marketing_site/js/account/config.js"
