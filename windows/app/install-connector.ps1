param([switch]$Uninstall)
$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
$manifestPath = Join-Path $appRoot 'native-host.json'
$hostName = 'org.fedtranslator.bridge'
$keys = @("HKCU:\Software\Google\Chrome\NativeMessagingHosts\$hostName", "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\$hostName")
if ($Uninstall) {
    foreach ($key in $keys) {
        if ((Test-Path -LiteralPath $key) -and (Get-Item -LiteralPath $key).GetValue('') -eq $manifestPath) {
            Remove-Item -LiteralPath $key
        }
    }
    Write-Output 'Connector registration removed. Your saved translations and login have been kept.'
    exit
}
if (-not (Test-Path -LiteralPath (Join-Path $appRoot '.runtime\python\python.exe'))) { throw 'Extract the entire ZIP first.' }
$manifest = [ordered]@{
    name = $hostName
    description = 'Fed and English live translation - local connector'
    path = (Join-Path $appRoot 'NativeHost.cmd')
    type = 'stdio'
    allowed_origins = @('chrome-extension://kiceknjkkhbfedilkgiegndlehnffmcc/')
}
$json = $manifest | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($manifestPath, $json, (New-Object System.Text.UTF8Encoding($false)))
foreach ($key in $keys) {
    New-Item -Path $key -Force | Out-Null
    Set-Item -LiteralPath $key -Value $manifestPath
}
Write-Output 'Installed for your Windows account in Chrome and Edge.'
Write-Output 'Next: open the browser Extensions page, enable Developer mode, and Load unpacked -> extension.'
Write-Output "Extension folder: $(Join-Path $appRoot 'extension')"
Write-Output 'Keep this extracted folder in place. If moved, run Install-Connector.cmd again.'
