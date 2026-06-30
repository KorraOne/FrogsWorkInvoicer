# Start account API + desktop app in separate PowerShell windows.
# Usage:
#   .\scripts\start-dev.ps1
#   .\scripts\start-dev.ps1 -DevBrowser

param(
    [switch]$DevBrowser
)

. "$PSScriptRoot\_dev-env.ps1"

Write-Host "Opening two terminals: account API, then desktop app..."
Start-FrogsWorkApiTerminal
Start-Sleep -Seconds 2
Start-FrogsWorkAppTerminal -DevBrowser:$DevBrowser

Write-Host ""
Write-Host "API:  $(Get-FrogsWorkAccountApiUrl)"
Write-Host "App:  http://127.0.0.1:5000/"
Write-Host "Stripe: copy account_api\dev\.dev.vars.example to .dev.vars; run .\scripts\configure-payment-links.ps1 once after setup."
