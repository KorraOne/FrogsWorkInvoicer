#Requires -Version 5.1
<#
.SYNOPSIS
  Fetch GET /metrics/summary and write a local HTML dashboard (gitignored copy).
#>
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $here ".env"
if (-not (Test-Path $envFile)) {
  Write-Error "Missing $envFile — copy .env.example to .env and set METRICS_TOKEN."
}

$apiBase = "https://api.frogswork.com"
$token = ""
Get-Content $envFile | ForEach-Object {
  $line = $_.Trim()
  if (-not $line -or $line.StartsWith("#")) { return }
  $parts = $line.Split("=", 2)
  if ($parts.Count -lt 2) { return }
  $k = $parts[0].Trim()
  $v = $parts[1].Trim()
  if ($k -eq "API_BASE") { $apiBase = $v.TrimEnd("/") }
  if ($k -eq "METRICS_TOKEN") { $token = $v }
}
if (-not $token) { Write-Error "METRICS_TOKEN is empty in .env" }

$uri = "$apiBase/metrics/summary"
Write-Host "GET $uri"
$headers = @{ Authorization = "Bearer $token"; Accept = "application/json" }
$json = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get
$jsonPath = Join-Path $here "last-summary.json"
$json | ConvertTo-Json -Depth 12 | Set-Content -Path $jsonPath -Encoding utf8

$pretty = ($json | ConvertTo-Json -Depth 12)
$html = @"
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>FrogsWork metrics (local)</title>
  <style>
    body { font-family: Georgia, serif; margin: 2rem; background: #f6f3ee; color: #1a1a1a; }
    h1 { font-size: 1.6rem; }
    .note { color: #555; margin-bottom: 1.5rem; }
    section { margin: 1.25rem 0; padding: 1rem 1.25rem; background: #fff; border: 1px solid #ddd; }
    h2 { margin: 0 0 0.75rem; font-size: 1.1rem; }
    pre { white-space: pre-wrap; word-break: break-word; font-size: 0.85rem; }
    table { border-collapse: collapse; width: 100%; }
    td, th { text-align: left; padding: 0.35rem 0.5rem; border-bottom: 1px solid #eee; }
  </style>
</head>
<body>
  <h1>FrogsWork product metrics</h1>
  <p class="note">Local-only view. Generated $(Get-Date -Format o). Source: <code>$uri</code></p>
  <section>
    <h2>Raw summary JSON</h2>
    <pre id="raw"></pre>
  </section>
  <script>
    const data = $pretty;
    document.getElementById("raw").textContent = JSON.stringify(data, null, 2);
  </script>
</body>
</html>
"@

$dashPath = Join-Path $here "dashboard.html"
Set-Content -Path $dashPath -Value $html -Encoding utf8
Write-Host "Wrote $jsonPath"
Write-Host "Wrote $dashPath"
Start-Process $dashPath
