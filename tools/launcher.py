"""Single-window launcher: keeps exactly ONE console for status & shutdown.
Backend + frontend run hidden in the background; Ctrl+C (or closing this
window) stops everything."""
import os
import subprocess
import sys
import time
import webbrowser

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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

procs = []

backend = subprocess.Popen(
    [
        PY, "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1", "--port", "8000", "--app-dir", BACKEND,
    ],
    env=env,
    stdout=backend_log,
    stderr=backend_log,
    creationflags=CREATE_NO_WINDOW,
)
procs.append(backend)

frontend = subprocess.Popen(
    f'cd /d "{FRONTEND}" && npm run dev',
    shell=True,
    stdout=frontend_log,
    stderr=frontend_log,
    creationflags=CREATE_NO_WINDOW,
)
procs.append(frontend)

time.sleep(5)
webbrowser.open("http://localhost:5173")

print()
print("  ==========================================")
print("    临时root 已启动" + ("  (MOCK 模式)" if MOCK else ""))
print("    浏览器: http://localhost:5173")
print("    后端  : http://127.0.0.1:8000   日志 logs/backend.log")
print("    按 Ctrl+C（或关闭本窗口）停止全部服务")
print("  ==========================================")
print()


def shutdown():
    print("正在停止服务...")
    for p in procs:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(p.pid)],
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            try:
                p.terminate()
            except Exception:
                pass
    print("已停止。")
    sys.exit(0)


try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print()
    shutdown()
