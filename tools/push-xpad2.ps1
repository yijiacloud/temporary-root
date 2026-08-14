# Pushes the vendored xpad2 arm64 ELF to the device.
param(
  [string]$Binary = "",
  [string]$Serial = ""
)
$ErrorActionPreference = "Stop"
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Binary) {
  $Binary = Join-Path $base "xpad2\xpad2"
  if (-not (Test-Path $Binary)) {
    Write-Host "Missing vendored xpad2 binary ($Binary). Put it there or pass -Binary <path>." -ForegroundColor Yellow
    exit 1
  }
}
$adb = Join-Path $base "platform-tools\adb.exe"
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
