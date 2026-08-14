# Pushes a downloaded xpad2 arm64 ELF to the device.
param(
  [string]$Binary = "",
  [string]$Serial = ""
)
$ErrorActionPreference = "Stop"
if (-not $Binary) {
  Write-Host "Usage: push-xpad2.ps1 -Binary <path-to-xpad2-arm64> [-Serial <serial>]" -ForegroundColor Yellow
  exit 1
}
$adb = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "platform-tools\adb.exe"
if (-not (Test-Path $adb)) {
  Write-Host "Missing adb. Run tools/bootstrap.ps1 first." -ForegroundColor Red
  exit 1
}
$s = if ($Serial) { @("-s", $Serial) } else { @() }
$remote = "/data/local/tmp/xpad2"
& $adb @s push $Binary $remote
& $adb @s shell "chmod 700 $remote"
# Confirm it is actually on the device.
& $adb @s shell "/data/local/tmp/xpad2 version"
