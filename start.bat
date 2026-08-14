@echo off
setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
set "PY=D:\superroot\python\python.exe"
set "ADB=%ROOT%tools\platform-tools\adb.exe"
set "XPAD2=%ROOT%tools\xpad2\xpad2"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"

cd /d "%ROOT%"

echo ========================================
echo   LinShiRoot (temporary root)
echo ========================================
echo.

if not exist "%PY%" (
  echo [x] Python missing: %PY%
  pause
  exit /b 1
)

if not exist "%ADB%" (
  echo [x] adb missing. Run tools\bootstrap.ps1
  pause
  exit /b 1
)

if /i not "%~1"=="mock" (
  set "SERIAL="
  for /f "tokens=1" %%s in ('"%ADB%" devices ^| findstr /r "device$"') do set "SERIAL=%%s"
  if defined SERIAL (
    echo [*] device !SERIAL! detected, pushing xpad2...
    "%ADB%" -s !SERIAL! push "%XPAD2%" /data/local/tmp/xpad2
    "%ADB%" -s !SERIAL! shell chmod 700 /data/local/tmp/xpad2
  ) else (
    echo [!] no authorized device, skip push
  )
) else (
  echo [*] mock mode, no device needed
)
echo.

if /i "%~1"=="mock" (
  start "xpad2-backend" cmd /k "set XPAD2_MOCK=1 && %PY% -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir %BACKEND%"
) else (
  start "xpad2-backend" cmd /k "%PY% -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir %BACKEND%"
)

start "xpad2-frontend" cmd /k "cd /d %FRONTEND% && npm run dev"

timeout /t 4 /nobreak >nul
start http://localhost:5173

echo.
echo [OK] backend 8000 / frontend 5173 opened
pause
