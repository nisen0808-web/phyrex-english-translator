param([switch]$NoBrowser, [int]$Port = 8878)
$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
$runtimePython = Join-Path $appRoot '.runtime\python\python.exe'
if (-not (Test-Path -LiteralPath $runtimePython)) { throw 'Extract the entire ZIP before starting this app.' }
$stateDir = if ($env:FED_TRANSLATOR_USER_DIR) { $env:FED_TRANSLATOR_USER_DIR } else { Join-Path $appRoot 'user-data' }
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$url = "http://127.0.0.1:$Port"
$running = $false
$health = $null
try { $health = Invoke-RestMethod "$url/api/config" -TimeoutSec 2 } catch { }
if ($health) {
    $appInstance = & $runtimePython -B -c "from runtime import instance_id; print(instance_id())"
    if ($health.distribution -ne 'public' -or $health.instance -ne $appInstance) { throw 'Another application or copy of this translator is using this port. Stop it first.' }
    $running = $true
}
if (-not $running) {
    $argsLine = '-B -X utf8 "' + (Join-Path $appRoot 'app.py') + '" --port ' + $Port
    $process = Start-Process -FilePath $runtimePython -ArgumentList $argsLine -WorkingDirectory $appRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $stateDir 'service.log') -RedirectStandardError (Join-Path $stateDir 'service-error.log')
    for ($attempt=0; $attempt -lt 40; $attempt++) {
        try { $health = Invoke-RestMethod "$url/api/config" -TimeoutSec 1; if ($health.distribution -eq 'public') { $running=$true; break } } catch { }
        Start-Sleep -Milliseconds 500
        if ($process.HasExited) { throw 'The connection component stopped. See user-data/service-error.log.' }
    }
}
if (-not $running) { throw 'The connection component did not become ready.' }
if (-not $NoBrowser) {
    $browserCandidates = @(
        (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
        (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe'),
        (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe')
    )
    $browserPath = $browserCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($browserPath) { Start-Process -FilePath $browserPath -ArgumentList $url -WindowStyle Normal }
    else { Start-Process $url -WindowStyle Normal }
}
Write-Output "Ready: $url"
