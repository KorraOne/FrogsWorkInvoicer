# Start FrogsWork desktop app in a new PowerShell window.
# Usage:
#   .\scripts\start-dev-app.ps1
#   .\scripts\start-dev-app.ps1 -DevBrowser

param(
    [switch]$DevBrowser
)

. "$PSScriptRoot\_dev-env.ps1"

Import-FrogsWorkDevVars
Write-Host "Starting FrogsWork app (API: $(Get-FrogsWorkAccountApiUrl)) ..."
if (-not $env:STRIPE_PAYMENT_LINK_MONTHLY -or -not $env:STRIPE_PAYMENT_LINK_ANNUAL) {
    Write-Host "Tip: add STRIPE_PAYMENT_LINK_MONTHLY and STRIPE_PAYMENT_LINK_ANNUAL to frogswork_api\.dev.vars"
}
Start-FrogsWorkAppTerminal -DevBrowser:$DevBrowser
