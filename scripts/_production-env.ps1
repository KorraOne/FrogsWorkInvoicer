# Load client_app/production.env for release builds and Stripe setup scripts.

$script:ProductionEnvPath = Join-Path (Split-Path $PSScriptRoot -Parent) "client_app\production.env"

function Import-ProductionEnv {
    if (-not (Test-Path $ProductionEnvPath)) {
        return @{}
    }
    $vars = @{}
    foreach ($line in Get-Content $ProductionEnvPath -Encoding UTF8) {
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith("#") -or $line -notmatch "=") { continue }
        $name, $value = $line -split "=", 2
        $name = $name.Trim()
        $value = $value.Trim()
        if ($name) { $vars[$name] = $value }
    }
    return $vars
}

function Require-ProductionPaymentLinks {
    $vars = Import-ProductionEnv
    $monthly = $vars["STRIPE_PAYMENT_LINK_MONTHLY"]
    $annual = $vars["STRIPE_PAYMENT_LINK_ANNUAL"]
    if (-not $monthly -or -not $annual) {
        throw @"
Missing Stripe Payment Links for release build.

1. Copy client_app\production.env.example to client_app\production.env
2. Add your Stripe Payment Link URLs (Dashboard → Payment links)
3. Re-run the build
"@
    }
    return $vars
}
