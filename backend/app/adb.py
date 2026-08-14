"""Adb subprocess boundary. The only code in the backend that touches adb.

When XPAD2_MOCK=1 run_command returns canned output so the whole stack is
testable and demoable without a device or an adb binary.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

ADB_BIN = ("adb",)
XPAD2_DEVICE_PATH = "/data/local/tmp/xpad2"


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
