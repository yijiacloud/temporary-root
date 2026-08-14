"""Adb subprocess boundary. The only code in the backend that touches adb.

When XPAD2_MOCK=1 run_command returns canned output so the whole stack is
testable and demoable without a device or an adb binary.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path


def _find_adb() -> str:
    """Locate the adb binary. Order:
    1. XPAD2_ADB env var (explicit override)
    2. vendored <project>/tools/platform-tools/adb.exe
    3. fall back to "adb" on PATH
    """
    env = os.environ.get("XPAD2_ADB")
    if env:
        return env
    # backend/app/adb.py -> parent.parent = backend -> parent = project root
    project_root = Path(__file__).resolve().parent.parent.parent
    for name in ("adb.exe", "adb"):
        candidate = project_root / "tools" / "platform-tools" / name
        if candidate.exists():
            return str(candidate)
    return "adb"


ADB_BIN = (_find_adb(),)
XPAD2_DEVICE_PATH = f"/data/local/tmp/xpad2-{date.today():%Y%m%d}"


def _find_local_xpad2() -> str | None:
    """Path to the vendored xpad2 ELF, if present under tools/xpad2/."""
    project_root = Path(__file__).resolve().parent.parent.parent
    candidate = project_root / "tools" / "xpad2" / "xpad2"
    return str(candidate) if candidate.exists() else None


XPAD2_LOCAL_PATH = _find_local_xpad2()


@dataclass
class AdbResult:
    stdout: str
    stderr: str
    exit_code: int

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def _mock() -> bool:
    return os.environ.get("XPAD2_MOCK", "") == "1"


_MOCK_OUTPUTS: dict[str, AdbResult] = {
    "status --json": AdbResult(
        stdout=(
            '{"product_version":"0.7.4","product_supported":true,"supported":true,'
            '"device_profile":"xpad2-v260-v272","boot_id":"mock-boot-1",'
            '"selinux":"Enforcing","temporary_root":{"id":"temporary-root",'
            '"state":"absent"},"components":['
            '{"id":"ota","state":"active","detail":"frozen"},'
            '{"id":"ksu","state":"active","detail":"version=32547 late-load"},'
            '{"id":"suu","state":"ready","detail":"another runtime active"},'
            '{"id":"vector","state":"absent"}]}'
        ),
        stderr="",
        exit_code=0,
    ),
    "version": AdbResult(stdout="xpad2 0.7.4 (catalog 2026-07-29.2)", stderr="", exit_code=0),
    "root": AdbResult(
        stdout=(
            "✓ ota: frozen\n"
            "✓ IonStack profile: xpad2-v260-v272 (exact)\n"
            "HOLDER attempt=1/6\n"
            "HOLDER attempt=2/6\n"
            "临时 Root 已验证并保留在当前启动周期\n"
        ),
        stderr="",
        exit_code=0,
    ),
    "doctor": AdbResult(stdout="[OK] XPad2 product family\n[OK] SELinux Enforcing\n", stderr="", exit_code=0),
    "list": AdbResult(stdout="ksu runtime KernelSU\nfull bundle default: ksu\n", stderr="", exit_code=0),
    "install": AdbResult(
        stdout=(
            "xpad2 install\n"
            "→ 读取目录 /data/local/tmp/xpad2\n"
            "✓ 设备支持: xpad2-v260-v272 (exact)\n"
            "→ 触发临时 Root (IonStack)...\n"
            "  holder 探测 attempt=1/6\n"
            "  holder 探测 attempt=2/6\n"
            "  holder 探测 attempt=3/6\n"
            "✓ 临时 Root 已取得\n"
            "→ 安装组件...\n"
            "✓ KernelSU 已安装 (late-load)\n"
            "⚠ 需要重启设备后才能生效\n"
        ),
        stderr="",
        exit_code=0,
    ),
}


def xpad2_argv(*rest: str) -> list[str]:
    """Build the device-side argv that invokes the xpad2 binary."""
    return [XPAD2_DEVICE_PATH, *rest]


def run_command(args: list[str], serial: str | None = None) -> AdbResult:
    """Run an adb command. args is the device-side argv (already starts with
    the xpad2 path or a bare shell builtin-style command)."""
    if _mock():
        key = " ".join(arg for arg in args if not arg.startswith("/data/local/tmp"))
        if key not in _MOCK_OUTPUTS:
            head = key.split(" ", 1)[0]
            if head in _MOCK_OUTPUTS:  # e.g. "install ksu suu" -> "install"
                return _MOCK_OUTPUTS[head]
            return AdbResult(
                stdout="",
                stderr=f"mock: unsupported command [{key}]",
                exit_code=1,
            )
        return _MOCK_OUTPUTS[key]

    argv = [*ADB_BIN, *((["-s", serial]) if serial else []), "shell", *args]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    return AdbResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)


def list_devices_raw(serial: str | None = None) -> AdbResult:
    """Return the raw `adb devices -l` output."""
    if _mock():
        return AdbResult(
            stdout=(
                "List of devices attached\n"
                "abc123 device product:ls12 model:XPad2 device:ls12_mt8797_wifi_64\n"
            ),
            stderr="",
            exit_code=0,
        )
    argv = [*ADB_BIN, "devices", "-l"]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=15)
    return AdbResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)


def ensure_xpad2_pushed(serial: str | None = None) -> dict:
    """Push the vendored xpad2 ELF to /data/local/tmp if the device lacks a
    usable copy. Non-fatal: returns a status dict rather than raising, so a
    missing device or binary never crashes startup."""
    if _mock() or not XPAD2_LOCAL_PATH:
        return {"pushed": False, "reason": "mock-or-missing-local-binary"}

    if serial is None:
        from . import device as _device

        devices = _device.parse_devices(list_devices_raw().stdout)
        online = [d for d in devices if d.state == "device"]
        if not online:
            return {"pushed": False, "reason": "no-authorized-device"}
        serial = online[0].serial

    check = run_command(
        ["sh", "-c", f"test -x {XPAD2_DEVICE_PATH} && echo yes || echo no"], serial
    )
    if "yes" in check.stdout:
        return {"pushed": False, "reason": "already-present", "serial": serial}

    push = subprocess.run(
        [*ADB_BIN, "-s", serial, "push", XPAD2_LOCAL_PATH, XPAD2_DEVICE_PATH],
        capture_output=True,
        text=True,
        timeout=180,
    )
    chmod = subprocess.run(
        [*ADB_BIN, "-s", serial, "shell", "chmod", "700", XPAD2_DEVICE_PATH],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {
        "pushed": push.returncode == 0,
        "serial": serial,
        "detail": (push.stdout + push.stderr + chmod.stdout + chmod.stderr).strip(),
    }
