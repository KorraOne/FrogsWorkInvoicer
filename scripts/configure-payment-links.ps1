# Set Stripe Payment Link "after payment" redirect to the local desktop app.
# Usage: .\scripts\configure-payment-links.ps1

. "$PSScriptRoot\_dev-env.ps1"
$python = Ensure-FrogsWorkApiDeps
Set-Location $ApiDir
& $python configure_payment_links.py
