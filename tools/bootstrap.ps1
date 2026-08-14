# Downloads Android Platform Tools (adb) into ./tools/platform-tools
# Delegates to download_adb.py (Python urllib) for a reliable TLS stack.
$ErrorActionPreference = "Stop"
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = Join-Path $base "platform-tools"
$py = "D:\superroot\python\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

if (-not (Test-Path (Join-Path $dest "adb.exe"))) {
    Write-Host "Downloading platform-tools..." -ForegroundColor Cyan
    & $py (Join-Path $base "download_adb.py")
}

Write-Host "adb available at: $dest\adb.exe" -ForegroundColor Green
& "$dest\adb.exe" version
