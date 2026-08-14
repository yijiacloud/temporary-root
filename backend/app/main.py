"""FastAPI application: REST + WebSocket front for xpad2 over adb."""
from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import adb, commands, device, executor, snapshot

logger = logging.getLogger("xpad2-console")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # On startup, push the vendored xpad2 ELF to /data/local/tmp so the
    # device is ready without a separate step (real mode only).
    pushed = adb.ensure_xpad2_pushed()
    if pushed.get("pushed"):
        logger.info("xpad2 pushed to %s", pushed.get("serial"))
    else:
        logger.info("xpad2 auto-push skipped: %s", pushed.get("reason"))
    yield


app = FastAPI(title="临时root", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_TASKS: dict[str, str] = {}  # id -> status


def _memory_path():
    return device._default_memory_path()


def _serial() -> str | None:
    return device.load(_memory_path()).selected_serial


class ExecRequest(BaseModel):
    command: list[str]
    serial: str | None = None


def _device_argv(command_parts: list[str]) -> list[str]:
    """Frontend sends bare command parts like ['status','--json'] or
    ['install','ksu']. Convert to device argv via the registry when the first
    token is a known command; otherwise prepend the xpad2 path verbatim."""
    if not command_parts:
        return [adb.XPAD2_DEVICE_PATH]
    head = command_parts[0]
    if head in commands.COMMANDS:
        return commands.build_argv(head, positional=list(command_parts[1:]))
    return [adb.XPAD2_DEVICE_PATH, *command_parts]


@app.get("/api/health")
def health() -> dict:
    devices = device.parse_devices(adb.list_devices_raw().stdout)
    return {
        "adb_available": not adb._mock(),
        "mock": adb._mock(),
        "device_count": len(devices),
        "selected_serial": _serial(),
    }


@app.get("/api/devices")
def list_devices() -> dict:
    devices = device.parse_devices(adb.list_devices_raw().stdout)
    return {"devices": [{"serial": d.serial, "state": d.state, **d.attrs} for d in devices]}


@app.post("/api/devices/select")
def select_device(body: dict) -> dict:
    serial = body.get("serial")
    mem = device.load(_memory_path())
    mem.selected_serial = serial
    device.save(mem, _memory_path())
    return {"ok": True, "selected_serial": serial}


@app.get("/api/status")
def get_status() -> dict:
    res = executor.run_sync([adb.XPAD2_DEVICE_PATH, "status", "--json"], _serial())
    snap = snapshot.parse_status(json.loads(res.stdout))
    return {
        "product_version": snap.product_version,
        "boot_id": snap.boot_id,
        "selinux": snap.selinux,
        "temporary_root": {
            "id": snap.temporary_root.id,
            "state": snap.temporary_root.state,
            "detail": snap.temporary_root.detail,
        },
        "components": [
            {"id": c.id, "state": c.state, "detail": c.detail} for c in snap.components
        ],
    }


@app.get("/api/components")
def get_components() -> dict:
    return {
        "commands": [
            {
                "id": s.id, "title": s.title, "readable": s.readable,
                "danger": s.danger, "long_running": s.long_running,
                "positional": list(s.positional), "flags": list(s.flags),
            }
            for s in commands.COMMANDS.values()
        ],
        "components": commands.COMPONENTS,
    }


@app.post("/api/exec")
def exec_command(req: ExecRequest) -> dict:
    argv = _device_argv(req.command)
    res = executor.run_sync(argv, req.serial or _serial())
    return {
        "stdout": res.stdout,
        "stderr": res.stderr,
        "exit_code": res.exit_code,
        "status": res.status.value,
    }


@app.post("/api/run")
def start_run(req: ExecRequest) -> dict:
    task_id = uuid.uuid4().hex
    _TASKS[task_id] = "queued"
    return {"task_id": task_id}


@app.post("/api/run/{task_id}/cancel")
def cancel_run(task_id: str) -> dict:
    _TASKS[task_id] = "cancelled"
    return {"ok": True, "task_id": task_id}


@app.websocket("/ws/run")
async def ws_run(ws: WebSocket, command: str) -> None:
    await ws.accept()
    argv = _device_argv(command.split())
    try:
        async for stream, line in executor.iter_lines(argv, _serial()):
            await ws.send_json({"type": "line", "stream": stream, "line": line})
        await ws.send_json({"type": "done"})
    except WebSocketDisconnect:
        return
    await ws.close()
