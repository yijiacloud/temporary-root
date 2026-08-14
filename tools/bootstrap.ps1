# Downloads Android Platform Tools (adb) into ./tools/platform-tools
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13

$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = Join-Path $base "platform-tools"
if (-not (Test-Path (Join-Path $dest "adb.exe"))) {
    $url = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
    $zip = Join-Path $base "platform-tools.zip"
    Write-Host "Downloading platform-tools..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $url -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $base -Force
    Remove-Item $zip
}
Write-Host "adb available at: $dest\adb.exe" -ForegroundColor Green
& "$dest\adb.exe" version
