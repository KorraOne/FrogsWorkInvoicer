# Shared helpers for local FrogsWork dev scripts.

$script:DevRoot = Split-Path $PSScriptRoot -Parent
$script:ApiDir = Join-Path $DevRoot "account_api\dev"
$script:AppDir = Join-Path $DevRoot "client_app"
$script:DevVarsPath = Join-Path $ApiDir ".dev.vars"
$script:ApiRequirements = Join-Path $ApiDir "requirements.txt"

function Get-FrogsWorkPython {
    $candidates = @(
        (Join-Path $DevRoot ".client-venv\Scripts\python.exe"),
        (Join-Path $ApiDir ".venv\Scripts\python.exe"),
        (Join-Path $DevRoot ".venv\Scripts\python.exe")
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) {
            return $path
        }
    }
    return (Get-Command python -ErrorAction Stop).Source
}

function Ensure-FrogsWorkApiDeps {
    $python = Get-FrogsWorkPython
    Write-Host "Checking API dependencies ($python)..."
    & $python -m pip install -q -r $ApiRequirements
    if ($LASTEXITCODE -ne 0) {
        throw "pip install failed for account_api/dev/requirements.txt"
    }
    return $python
}

function Import-FrogsWorkDevVars {
    if (-not (Test-Path $DevVarsPath)) {
        return @{}
    }
    $vars = @{}
    foreach ($line in Get-Content $DevVarsPath -Encoding UTF8) {
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith("#") -or $line -notmatch "=") {
            continue
        }
        $name, $value = $line -split "=", 2
        $name = $name.Trim()
        $value = $value.Trim()
        if ($name) {
            Set-Item -Path "Env:$name" -Value $value
            $vars[$name] = $value
        }
    }
    return $vars
}

function Get-DevVarsExportBlock {
    param([hashtable]$Vars)
    $lines = @()
    foreach ($key in @(
        "FROGSWORK_ACCOUNT_API_URL",
        "FROGSWORK_DESKTOP_APP_URL"
    )) {
        if ($Vars.ContainsKey($key) -and $Vars[$key]) {
            $escaped = $Vars[$key] -replace "'", "''"
            $lines += "`$env:$key = '$escaped'"
        }
    }
    return ($lines -join "`n")
}

function Get-FrogsWorkApiPort {
    $port = $env:FLASK_PORT
    if (-not $port) { $port = "8787" }
    return $port
}

function Get-FrogsWorkAccountApiUrl {
    $port = Get-FrogsWorkApiPort
    return "http://127.0.0.1:$port"
}

function Start-FrogsWorkApiTerminal {
    $python = Ensure-FrogsWorkApiDeps
    $port = Get-FrogsWorkApiPort
    $cmd = @"
Set-Location '$ApiDir'
`$env:FLASK_PORT = '$port'
& '$python' server.py
"@
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd
}

function Start-FrogsWorkAppTerminal {
    param(
        [switch]$DevBrowser
    )

    $devVars = Import-FrogsWorkDevVars
    $apiUrl = Get-FrogsWorkAccountApiUrl
    $devVars["FROGSWORK_ACCOUNT_API_URL"] = $apiUrl
    if (-not $devVars.ContainsKey("FROGSWORK_DESKTOP_APP_URL") -or -not $devVars["FROGSWORK_DESKTOP_APP_URL"]) {
        $devVars["FROGSWORK_DESKTOP_APP_URL"] = "https://app.frogswork.com"
    }
    $envBlock = Get-DevVarsExportBlock -Vars $devVars
    $python = Get-FrogsWorkPython
    if ($DevBrowser) {
        Write-Host "Note: -DevBrowser is obsolete (Flask UI removed). Opening Cloud desktop shell."
    }

    $cmd = @"
Set-Location '$AppDir'
$envBlock
& '$python' app.py
"@

    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd
}
