# Start FrogsWork account API (Flask) in a new PowerShell window.
# Usage: .\scripts\start-dev-api.ps1

. "$PSScriptRoot\_dev-env.ps1"

Write-Host "Starting account API at $(Get-FrogsWorkAccountApiUrl) ..."
Start-FrogsWorkApiTerminal
