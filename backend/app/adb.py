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


def _find_fastboot() -> str:
    """Locate the fastboot binary (vendored platform-tools first)."""
    env = os.environ.get("XPAD2_FASTBOOT")
    if env:
        return env
    project_root = Path(__file__).resolve().parent.parent.parent
    for name in ("fastboot.exe", "fastboot"):
        candidate = project_root / "tools" / "platform-tools" / name
        if candidate.exists():
            return str(candidate)
    return "fastboot"


FASTBOOT_BIN = _find_fastboot()


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
        if "--backend" in key:
            return AdbResult(
                stdout=(
                    "xpad-install install --backend\n"
                    "[+] INSTALL SUCCESS\n"
                    "package=com.example.target\n"
                ),
                stderr="",
                exit_code=0,
            )
        if key == "cleanup":
            return AdbResult(stdout="[+] cleanup 完成\n", stderr="", exit_code=0)
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


# ============ 安装 Apps（xpad-install ELF 后端）============
# vendor 自 xpad-safe-install：单文件 OEM APK 安装器，内部封装了
#   auto   → 走 OEM znxxservice Provider（Binder 后门）
#   direct → 在 0044 身份里创建 PackageInstaller session
XPAD_INSTALL_REMOTE = "/data/local/tmp/xpad-install"
APK_DEVICE_DIR = "/data/local/tmp"


def _find_local_xpad_install() -> str | None:
    """Vendored xpad-install ELF under tools/xpad-install/."""
    project_root = Path(__file__).resolve().parent.parent.parent
    candidate = project_root / "tools" / "xpad-install" / "xpad-install"
    return str(candidate) if candidate.exists() else None


XPAD_INSTALL_LOCAL = _find_local_xpad_install()


def ensure_xpad_install_pushed(serial: str | None = None) -> dict:
    """Push the xpad-install ELF to /data/local/tmp and chmod 755 if missing."""
    if _mock() or not XPAD_INSTALL_LOCAL:
        return {"pushed": False, "reason": "mock-or-missing-local-binary"}

    if serial is None:
        from . import device as _device

        devices = _device.parse_devices(list_devices_raw().stdout)
        online = [d for d in devices if d.state == "device"]
        if not online:
            return {"pushed": False, "reason": "no-authorized-device"}
        serial = online[0].serial

    check = run_command(
        ["sh", "-c", f"test -x {XPAD_INSTALL_REMOTE} && echo yes || echo no"], serial
    )
    if "yes" in check.stdout:
        return {"pushed": False, "reason": "already-present", "serial": serial}

    push = subprocess.run(
        [*ADB_BIN, "-s", serial, "push", XPAD_INSTALL_LOCAL, XPAD_INSTALL_REMOTE],
        capture_output=True,
        text=True,
        timeout=180,
    )
    chmod = subprocess.run(
        [*ADB_BIN, "-s", serial, "shell", "chmod", "755", XPAD_INSTALL_REMOTE],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {
        "pushed": push.returncode == 0,
        "serial": serial,
        "detail": (push.stdout + push.stderr + chmod.stdout + chmod.stderr).strip(),
    }


def push_apk(local_path: str, serial: str | None = None) -> dict:
    """Push an APK to /data/local/tmp on the device."""
    filename = os.path.basename(local_path)
    remote = f"{APK_DEVICE_DIR}/{filename}"
    if _mock():
        return {"pushed": True, "remote_path": remote, "detail": "mock push (no device)"}
    argv = [*ADB_BIN, *((["-s", serial]) if serial else []), "push", local_path, remote]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    return {
        "pushed": proc.returncode == 0,
        "remote_path": remote,
        "detail": (proc.stdout + proc.stderr).strip(),
    }


def install_apk_argv(remote_path: str, backend: str = "auto") -> list[str]:
    """Device-side argv: xpad-install install --backend <auto|direct> <apk>."""
    return [XPAD_INSTALL_REMOTE, "install", "--backend", backend, remote_path]


def cleanup_argv() -> list[str]:
    """Device-side argv: xpad-install cleanup."""
    return [XPAD_INSTALL_REMOTE, "cleanup"]


# ============ fastboot（一键 Root 流程）============
def fastboot_run(args: list[str], timeout: int = 120) -> AdbResult:
    """Run a fastboot command (device must be in fastboot mode)."""
    if _mock():
        return AdbResult(stdout="", stderr="", exit_code=0)
    argv = [FASTBOOT_BIN, *args]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return AdbResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)


def fastboot_devices() -> list[str]:
    """Serial numbers of devices currently in fastboot mode."""
    res = fastboot_run(["devices"], timeout=15)
    out = []
    for line in res.stdout.splitlines():
        parts = line.split()
        if parts:
            out.append(parts[0])
    return out


def reboot_bootloader(serial: str | None = None) -> AdbResult:
    """`adb reboot bootloader` — put the device into fastboot mode."""
    if _mock():
        return AdbResult(stdout="mock reboot bootloader", stderr="", exit_code=0)
    argv = [*ADB_BIN, *((["-s", serial]) if serial else []), "reboot", "bootloader"]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    return AdbResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)


def reboot_system() -> AdbResult:
    """`fastboot reboot` — reboot back to Android."""
    return fastboot_run(["reboot"], timeout=30)


# ============ 分区备份 / 刷写（su + dd）============
PARTITION_BY_NAME = "/dev/block/by-name/{name}"

BACKUP_DIR = os.path.join(os.path.expandvars(r"%USERPROFILE%\Desktop"), "backup")

# 一键 Root 默认文件目录（lk_old.img / boot.img / manger.apk）
ONECLICK_DIR = Path(__file__).resolve().parent.parent.parent / "tools" / "oneclick"


def shell_su_dd_read(partition: str, remote_tmp: str, serial: str | None = None) -> AdbResult:
    """Read a whole partition into a device-side temp file (requires su)."""
    if _mock():
        return AdbResult(stdout=f"mock dd read {partition}", stderr="", exit_code=0)
    cmd = f"su -c 'dd if={partition} of={remote_tmp} bs=4096 2>/dev/null'"
    return run_command(["sh", "-c", cmd], serial)


def shell_su_dd_write(remote_src: str, partition: str, serial: str | None = None) -> AdbResult:
    """Write a device-side file onto a partition (requires su, DESTRUCTIVE)."""
    if _mock():
        return AdbResult(stdout=f"mock dd write {partition}", stderr="", exit_code=0)
    cmd = f"su -c 'dd if={remote_src} of={partition} bs=4096 2>/dev/null'"
    return run_command(["sh", "-c", cmd], serial)


def pull_file(remote_path: str, local_path: str, serial: str | None = None) -> AdbResult:
    """`adb pull` a file from device to a local path."""
    if _mock():
        return AdbResult(stdout="mock pull", stderr="", exit_code=0)
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    argv = [*ADB_BIN, *((["-s", serial]) if serial else []), "pull", remote_path, local_path]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=600)
    return AdbResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)


def push_file(local_path: str, remote_path: str, serial: str | None = None) -> AdbResult:
    """`adb push` a local file to the device."""
    if _mock():
        return AdbResult(stdout="mock push file", stderr="", exit_code=0)
    argv = [*ADB_BIN, *((["-s", serial]) if serial else []), "push", local_path, remote_path]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=600)
    return AdbResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)
