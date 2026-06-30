# Start account API + desktop app in separate PowerShell windows.
# Usage:
#   .\scripts\start-dev.ps1
#   .\scripts\start-dev.ps1 -DevBrowser

param(
    [switch]$DevBrowser
)

. "$PSScriptRoot\_dev-env.ps1"

Write-Host "Configuring Stripe payment link redirects for local dev..."
& "$PSScriptRoot\configure-payment-links.ps1"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Warning: could not update payment links. Run manually: .\scripts\configure-payment-links.ps1"
}

Write-Host "Opening two terminals: account API, then desktop app..."
Start-FrogsWorkApiTerminal
Start-Sleep -Seconds 2
Start-FrogsWorkAppTerminal -DevBrowser:$DevBrowser

Write-Host ""
Write-Host "API:  $(Get-FrogsWorkAccountApiUrl)"
Write-Host "App:  http://127.0.0.1:5000/"
Write-Host "Payment links load from frogswork_api\.dev.vars (copy from .dev.vars.example)."
