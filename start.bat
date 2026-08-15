@echo off
chcp 65001 >nul
if /i "%~1"=="mock" (
  "D:\superroot\python\python.exe" "%~dp0tools\launcher.py" --mock
) else (
  "D:\superroot\python\python.exe" "%~dp0tools\launcher.py"
)
