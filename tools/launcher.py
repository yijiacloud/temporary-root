"""Hidden-window launcher: starts backend + frontend in the background and
opens the browser. Run via pythonw.exe (no console) from start.bat."""
import os
import subprocess
import sys
import time
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = r"D:\superroot\python\python.exe"
BACKEND = os.path.join(ROOT, "backend")
FRONTEND = os.path.join(ROOT, "frontend")
LOG_DIR = os.path.join(ROOT, "logs")

MOCK = "--mock" in sys.argv
CREATE_NO_WINDOW = 0x08000000

os.makedirs(LOG_DIR, exist_ok=True)
backend_log = open(os.path.join(LOG_DIR, "backend.log"), "w", encoding="utf-8")
frontend_log = open(os.path.join(LOG_DIR, "frontend.log"), "w", encoding="utf-8")

env = os.environ.copy()
if MOCK:
    env["XPAD2_MOCK"] = "1"

# backend (uvicorn)
subprocess.Popen(
    [
        PY, "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1", "--port", "8000", "--app-dir", BACKEND,
    ],
    env=env,
    stdout=backend_log,
    stderr=backend_log,
    creationflags=CREATE_NO_WINDOW,
)

# frontend (vite dev)
subprocess.Popen(
    f'cd /d "{FRONTEND}" && npm run dev',
    shell=True,
    stdout=frontend_log,
    stderr=frontend_log,
    creationflags=CREATE_NO_WINDOW,
)

# open the browser once the servers are up
time.sleep(5)
webbrowser.open("http://localhost:5173")
