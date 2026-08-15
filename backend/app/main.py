"""FastAPI application: REST + WebSocket front for xpad2 over adb."""
from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import adb, commands, device, executor, snapshot

app = FastAPI(title="临时root")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_TASKS: dict[str, str] = {}  # id -> status


def _memory_path():
    return device._default_memory_path()


_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"


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


def _push_reason_line(result: dict) -> str:
    """Turn an ensure_xpad2_pushed() result into one friendly log line."""
    if result.get("pushed"):
        return f"→ 已推送 xpad2 到 /data/local/tmp (serial={result.get('serial')})"
    reason = result.get("reason")
    if reason == "already-present":
        return "→ xpad2 已在设备上，跳过推送"
    if reason == "no-authorized-device":
        return "⚠ 未检测到已授权设备，无法推送 xpad2"
    if reason == "mock-or-missing-local-binary":
        return "⚠ 未找到本地 xpad2 二进制 (tools/xpad2/xpad2)，无法推送"
    return f"⚠ xpad2 推送跳过：{reason}"


def _install_reason_line(result: dict) -> str:
    if result.get("pushed"):
        return f"→ 已推送 xpad-install 到 /data/local/tmp (serial={result.get('serial')})"
    reason = result.get("reason")
    if reason == "already-present":
        return "→ xpad-install 已在设备上，跳过推送"
    if reason == "mock-or-missing-local-binary":
        return "⚠ 未找到本地 xpad-install (tools/xpad-install/)，无法推送"
    if reason == "no-authorized-device":
        return "⚠ 未检测到已授权设备，无法推送 xpad-install"
    return f"⚠ xpad-install 推送跳过：{reason}"


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


def _neutral_status() -> dict:
    """Fallback snapshot when the device-side xpad2 is missing or returned no
    JSON (e.g. before the first one-click root push)."""
    return {
        "product_version": None,
        "boot_id": None,
        "selinux": None,
        "temporary_root": {
            "id": "temporary-root",
            "state": "absent",
            "detail": "设备尚未安装 xpad2；点击「开始安装」会自动推送到 /data/local/tmp",
        },
        "components": [],
    }


@app.get("/api/status")
def get_status() -> dict:
    res = executor.run_sync([adb.XPAD2_DEVICE_PATH, "status", "--json"], _serial())
    raw = res.stdout.strip()
    if not raw:
        return _neutral_status()
    try:
        snap = snapshot.parse_status(json.loads(raw))
    except json.JSONDecodeError:
        return _neutral_status()
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
    push_line = ""
    head = req.command[0] if req.command else ""
    if head in ("install", "root") and not adb._mock():
        push_line = _push_reason_line(adb.ensure_xpad2_pushed(req.serial or _serial())) + "\n"
    argv = _device_argv(req.command)
    res = executor.run_sync(argv, req.serial or _serial())
    return {
        "stdout": push_line + res.stdout,
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
    parts = command.split()
    head = parts[0] if parts else ""
    if head in ("install", "root") and not adb._mock():
        await ws.send_json(
            {
                "type": "line",
                "stream": "stdout",
                "line": _push_reason_line(adb.ensure_xpad2_pushed(_serial())),
            }
        )
    argv = _device_argv(parts)
    try:
        async for stream, line in executor.iter_lines(argv, _serial()):
            await ws.send_json({"type": "line", "stream": stream, "line": line})
        await ws.send_json({"type": "done"})
    except WebSocketDisconnect:
        return
    await ws.close()


@app.post("/api/apk/upload")
async def upload_apk(file: UploadFile = File(...)) -> dict:
    """接收上传的 APK，保存到本地并 adb push 到设备 /data/local/tmp。"""
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = os.path.basename(file.filename or "upload.apk")
    if not filename.lower().endswith(".apk"):
        filename += ".apk"
    local = _UPLOAD_DIR / filename
    with open(local, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
    result = adb.push_apk(str(local), _serial())
    return {
        "filename": filename,
        "local_path": str(local),
        "remote_path": result["remote_path"],
        "size": local.stat().st_size,
        "pushed": result["pushed"],
        "detail": result["detail"],
    }


_PACKAGE_RE = re.compile(r"package=([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)")


@app.websocket("/ws/install_apk")
async def ws_install_apk(ws: WebSocket, remote: str, pkg: str = "") -> None:
    """触发设备端 xpad-install 安装指定 APK（流式回传日志，auto→direct 兜底）。"""
    await ws.accept()

    async def run(argv: list[str]) -> str:
        """Stream a device command and collect its stdout."""
        out: list[str] = []
        async for stream, line in executor.iter_lines(argv, _serial()):
            await ws.send_json({"type": "line", "stream": stream, "line": line})
            if stream == "stdout":
                out.append(line)
        return "\n".join(out)

    async def send(msg: str) -> None:
        await ws.send_json({"type": "line", "stream": "stdout", "line": msg})

    try:
        # 1. 推送 xpad-install
        tool = adb.ensure_xpad_install_pushed(_serial())
        await send(_install_reason_line(tool))

        # 2. auto 后端
        await send("→ 安装 (auto 后端)…")
        out = await run(adb.install_apk_argv(remote, "auto"))
        match = _PACKAGE_RE.search(out)

        # 3. direct 兜底
        if not match:
            await send("⚠ auto 后端未解析出包名，尝试 direct 后端兜底…")
            match = _PACKAGE_RE.search(await run(adb.install_apk_argv(remote, "direct")))

        # 4. cleanup
        await run(adb.cleanup_argv())

        if match:
            await send(f"✓ 安装成功，包名: {match.group(1)}")
        else:
            await send("⚠ 未能解析包名，请核对上方日志")
    except WebSocketDisconnect:
        return
    await ws.send_json({"type": "done"})
    await ws.close()


@app.post("/api/oneclick/upload")
async def upload_oneclick(file: UploadFile = File(...)) -> dict:
    """保存一键 Root 所需文件（lk_old/boot/apk），不 push，流程内统一处理。"""
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = os.path.basename(file.filename or "upload.bin")
    local = _UPLOAD_DIR / filename
    with open(local, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
    return {"filename": filename, "local_path": str(local), "size": local.stat().st_size}


_OC_TMP = "/data/local/tmp/oneclick"
_OC_STEPS = 7


def _default_oc(filename: str) -> str:
    """Default one-click file under tools/oneclick/, empty string if absent."""
    p = adb.ONECLICK_DIR / filename
    return str(p) if p.exists() else ""


@app.websocket("/ws/oneclick")
async def ws_oneclick(
    ws: WebSocket, lk_old: str = "", boot: str = "", apk: str = ""
) -> None:
    """一键 Root：临时root → 备份lk → 刷lk_old → fastboot → unlock → 刷boot → 装apk。"""
    await ws.accept()
    # 未显式传文件时回退到 tools/oneclick/ 默认文件
    lk_old = lk_old or _default_oc("lk_old.img")
    boot = boot or _default_oc("boot.img")
    apk = apk or _default_oc("manger.apk")

    async def log(stream: str, line: str) -> None:
        await ws.send_json({"type": "line", "stream": stream, "line": line})

    async def info(msg: str) -> None:
        await log("stdout", msg)

    async def progress(step: int, name: str) -> None:
        await ws.send_json(
            {"type": "progress", "step": step, "total": _OC_STEPS, "name": name}
        )

    async def run(argv: list[str]) -> None:
        async for stream, line in executor.iter_lines(argv, _serial()):
            await log(stream, line)

    async def run_sync(args: list[str]):
        res = adb.run_command(args, _serial())
        for line in res.stdout.splitlines():
            await log("stdout", line)
        for line in res.stderr.splitlines():
            await log("stderr", line)
        return res

    async def emit_result(res, label: str = "") -> None:
        for line in res.stdout.splitlines():
            if line.strip():
                await log("stdout", line)
        for line in res.stderr.splitlines():
            if line.strip():
                await log("stderr", line)

    serial = _serial()
    idx = 0

    async def next_step(name: str) -> None:
        nonlocal idx
        idx += 1
        await progress(idx, name)
        await info(f"—— 步骤 {idx}/{_OC_STEPS}: {name} ——")

    try:
        # 1. 临时 root（不提示）
        await next_step("临时 Root")
        if not adb._mock():
            await info(_push_reason_line(adb.ensure_xpad2_pushed(serial)))
        await run([adb.XPAD2_DEVICE_PATH, "root"])

        # 2. 备份 lk_a / lk_b
        await next_step("备份 lk_a / lk_b")
        for name in ("lk_a", "lk_b"):
            part = adb.PARTITION_BY_NAME.format(name=name)
            tmp = f"{_OC_TMP}/{name}.img"
            if not adb._mock():
                run_command_result = adb.shell_su_dd_read(part, tmp, serial)
                await emit_result(run_command_result)
            local = os.path.join(adb.BACKUP_DIR, f"{name}.img")
            await info(f"→ 备份到 {local}")
            await emit_result(adb.pull_file(tmp, local, serial))

        # 3. 刷 lk_old → lk_a
        await next_step("刷入 lk_old → lk_a")
        if not os.path.isfile(lk_old):
            raise RuntimeError(f"缺少 lk_old 文件：{lk_old}")
        remote_lk = f"{_OC_TMP}/lk_old.img"
        await info(f"→ push {lk_old}")
        await emit_result(adb.push_file(lk_old, remote_lk, serial))
        await info("→ dd 刷入 lk_a")
        await emit_result(
            adb.shell_su_dd_write(remote_lk, adb.PARTITION_BY_NAME.format(name="lk_a"), serial)
        )

        # 4. 进入 fastboot 并等待
        await next_step("重启到 fastboot")
        await info("→ adb reboot bootloader")
        await emit_result(adb.reboot_bootloader(serial))
        await info("→ 等待设备进入 fastboot…")
        fb: list[str] = []
        for _ in range(90):
            fb = adb.fastboot_devices()
            if fb:
                break
            await asyncio.sleep(2)
        if not fb:
            raise RuntimeError("等待 fastboot 超时（180s）")
        await info(f"✓ fastboot 设备：{fb[0]}")

        # 5. unlock
        await next_step("解锁 (flashing unlock)")
        await emit_result(adb.fastboot_run(["flashing", "unlock"], timeout=60))

        # 6. 刷 boot_a / boot_b
        await next_step("刷入 boot_a / boot_b")
        if not os.path.isfile(boot):
            raise RuntimeError(f"缺少 boot 文件：{boot}")
        for slot in ("boot_a", "boot_b"):
            await info(f"→ fastboot flash {slot} {boot}")
            await emit_result(adb.fastboot_run(["flash", slot, boot], timeout=600))

        # 7. 重启 + 装 apk
        await next_step("重启并安装 APK")
        await info("→ fastboot reboot")
        await emit_result(adb.reboot_system())
        await info("→ 等待设备回到系统…")
        online = False
        for _ in range(90):
            devs = device.parse_devices(adb.list_devices_raw().stdout)
            if any(d.state == "device" for d in devs):
                online = True
                break
            await asyncio.sleep(2)
        if not online:
            raise RuntimeError("等待设备回到系统超时（180s）")
        await info("✓ 设备已上线")
        if os.path.isfile(apk):
            await info("→ 安装 APK…")
            pushed = adb.push_apk(apk, serial)
            await info(f"→ remote: {pushed['remote_path']}")
            out = ""
            async for stream, line in executor.iter_lines(
                adb.install_apk_argv(pushed["remote_path"], "auto"), serial
            ):
                await log(stream, line)
                if stream == "stdout":
                    out += line + "\n"
            m = _PACKAGE_RE.search(out)
            if not m:
                await info("⚠ auto 未解析包名，direct 兜底…")
                async for stream, line in executor.iter_lines(
                    adb.install_apk_argv(pushed["remote_path"], "direct"), serial
                ):
                    await log(stream, line)
                    if stream == "stdout":
                        out += line + "\n"
                m = _PACKAGE_RE.search(out)
            await run(adb.cleanup_argv())
            await info(f"✓ 安装成功，包名：{m.group(1)}" if m else "⚠ 未能解析包名")
        else:
            await info("⚠ 未提供 APK，跳过安装")

        await info("======== 一键 Root 完成 ========")
    except WebSocketDisconnect:
        return
    except Exception as e:  # noqa: BLE001
        await info(f"⚠ 失败：{e}")
        await ws.send_json({"type": "failed", "message": str(e)})
        await ws.close()
        return
    await ws.send_json({"type": "done"})
    await ws.close()
