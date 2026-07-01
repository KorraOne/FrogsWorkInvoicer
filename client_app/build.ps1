# Build FrogsWork desktop client (run from client_app/)

param(
    [switch]$OneFile,
    [switch]$Clean,
    [switch]$SkipVenv,
    [Alias("BillingUrl")]
    [string]$AccountApiUrl = "",
    [string]$PaymentLinkMonthly = "",
    [string]$PaymentLinkAnnual = ""
)

$ErrorActionPreference = "Stop"
$AppDir = $PSScriptRoot
$RepoRoot = Split-Path $AppDir -Parent
$ConfigFile = Join-Path $AppDir "app_config.py"
$VenvDir = Join-Path $RepoRoot ".client-venv"
$Requirements = Join-Path $AppDir "requirements.txt"
$DistOnedir = Join-Path $AppDir "dist\FrogsWork"
$DistOneFile = Join-Path $AppDir "dist\FrogsWork.exe"

function Stop-RunningApp {
    Get-Process -Name "FrogsWork" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue |
        ForEach-Object {
            $procId = $_.OwningProcess
            if ($procId -and $procId -ne 0) {
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            }
        }
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -in @("python.exe", "pythonw.exe") -and $_.CommandLine -match "client_app\\app\.py" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

Set-Location $AppDir
Stop-RunningApp

$configBackup = $null
$needsRestore = $false

function Patch-AppConfigLine {
    param([string]$Content, [string]$Name, [string]$Value)
    if (-not $Value) { return $Content }
    $pattern = "(?m)^$Name = os\.environ\.get\(""[^""]*"", ""[^""]*""\)\.strip\(\)"
    $replacement = "$Name = os.environ.get(""$Name"", ""$Value"").strip()"
    if ($Content -notmatch $pattern) {
        throw "Could not patch $Name in app_config.py"
    }
    return ($Content -replace $pattern, $replacement)
}

if ($AccountApiUrl -or $PaymentLinkMonthly -or $PaymentLinkAnnual) {
    $configBackup = Get-Content $ConfigFile -Raw
    $updated = $configBackup
    if ($AccountApiUrl) {
        $escaped = [regex]::Escape("http://127.0.0.1:8787")
        $updated = $updated -replace $escaped, $AccountApiUrl
        if ($updated -eq $configBackup) {
            throw "Could not patch app_config.py with AccountApiUrl. Check DEFAULT_ACCOUNT_API_URL default."
        }
        Write-Host "Using account API URL for this build: $AccountApiUrl"
    }
    if ($PaymentLinkMonthly) {
        $updated = Patch-AppConfigLine -Content $updated -Name "STRIPE_PAYMENT_LINK_MONTHLY" -Value $PaymentLinkMonthly
        Write-Host "Baking monthly Payment Link into build."
    }
    if ($PaymentLinkAnnual) {
        $updated = Patch-AppConfigLine -Content $updated -Name "STRIPE_PAYMENT_LINK_ANNUAL" -Value $PaymentLinkAnnual
        Write-Host "Baking annual Payment Link into build."
    }
    Set-Content -Path $ConfigFile -Value $updated -NoNewline
    $needsRestore = $true
}

try {
    if (-not $SkipVenv) {
        if (-not (Test-Path $VenvDir)) {
            python -m venv $VenvDir
        }
        $python = Join-Path $VenvDir "Scripts\python.exe"
        $pyinstaller = Join-Path $VenvDir "Scripts\pyinstaller.exe"
        & $python -m pip install -q -r $Requirements
    } else {
        $pyinstaller = "pyinstaller"
    }

    if ($Clean) {
        Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
    }

    if ($OneFile) {
        $env:FROGSWORK_ONEFILE = "1"
    } else {
        $env:FROGSWORK_ONEFILE = "0"
    }

    & $pyinstaller FrogsWork.spec --noconfirm --log-level WARN
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $ExeConfig = Join-Path $AppDir "FrogsWork.exe.config"
    if (-not $OneFile -and (Test-Path $ExeConfig)) {
        Copy-Item -Force $ExeConfig (Join-Path $DistOnedir "FrogsWork.exe.config")
    }

    if ($OneFile) {
        Write-Host "Output: $DistOneFile"
    } else {
        Write-Host "Output: $DistOnedir\FrogsWork.exe"
    }
    Write-Host "Requires Microsoft Edge WebView2 Runtime on target PCs."
}
finally {
    if ($needsRestore -and $null -ne $configBackup) {
        Set-Content -Path $ConfigFile -Value $configBackup -NoNewline
    }
}
