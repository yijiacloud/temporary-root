@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
set "PY=D:\superroot\python\python.exe"
set "ADB=%ROOT%tools\platform-tools\adb.exe"
set "XPAD2=%ROOT%tools\xpad2\xpad2"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"

cd /d "%ROOT%"

echo ==============================================
echo   xpad2 Console  -  one-click launcher
echo ==============================================
echo.

if not exist "%PY%" (
  echo [x] Python 缺失: %PY%
  echo     请确认 D:\superroot\python 存在
  pause & exit /b 1
)
if not exist "%ADB%" (
  echo [x] adb 缺失，运行 tools\bootstrap.ps1 下载
  pause & exit /b 1
)

rem ---- 1. push xpad2 (real mode auto-detects device) ----
if /i not "%~1"=="mock" (
  set "SERIAL="
  for /f "tokens=1" %%s in ('"%ADB%" devices ^| findstr /r "device$"') do set "SERIAL=%%s"
  if defined SERIAL (
    echo [*] 检测到设备 !SERIAL!，推送 xpad2 ...
    "%ADB%" -s !SERIAL! push "%XPAD2%" /data/local/tmp/xpad2
    "%ADB%" -s !SERIAL! shell chmod 700 /data/local/tmp/xpad2
    echo.
  ) else (
    echo [!] 未检测到已授权的设备，跳过推送（后端将以无设备模式运行）
    echo.
  )
) else (
  echo [*] mock 模式：无需设备
  echo.
)

rem ---- 2. start backend ----
if /i "%~1"=="mock" (
  start "xpad2-backend" cmd /k "set XPAD2_MOCK=1 && %PY% -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir %BACKEND%"
) else (
  start "xpad2-backend" cmd /k "%PY% -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir %BACKEND%"
)

rem ---- 3. start frontend ----
start "xpad2-frontend" cmd /k "cd /d %FRONTEND% && npm run dev"

rem ---- 4. open browser ----
timeout /t 4 /nobreak >nul
start http://127.0.0.1:5173

echo.
echo [OK] 后端 http://127.0.0.1:8000   前端 http://127.0.0.1:5173
echo      浏览器已打开。关闭对应窗口即可停止服务。
echo.
pause
