@echo off
if /i "%~1"=="mock" (
  start "" "D:\superroot\python\pythonw.exe" "%~dp0tools\launcher.py" --mock
) else (
  start "" "D:\superroot\python\pythonw.exe" "%~dp0tools\launcher.py"
)
