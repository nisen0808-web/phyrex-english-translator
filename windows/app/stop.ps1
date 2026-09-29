$ErrorActionPreference = 'Stop'
$stateDir = Join-Path $PSScriptRoot 'user-data'
$pidFile = Join-Path $stateDir 'server.pid'
if (Test-Path -LiteralPath $pidFile) {
    $serverPid = [int](Get-Content -LiteralPath $pidFile -Raw)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $serverPid" -ErrorAction SilentlyContinue
    $expected = Join-Path $PSScriptRoot 'app.py'
    if ($process -and $process.CommandLine.Contains($expected)) { Stop-Process -Id $serverPid }
    Remove-Item -LiteralPath $pidFile
}
