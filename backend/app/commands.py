"""Declarative xpad2 command registry and argv builder."""
from __future__ import annotations

from dataclasses import dataclass, field

from .adb import XPAD2_DEVICE_PATH


@dataclass(frozen=True)
class CommandSpec:
    id: str
    title: str
    readable: bool
    danger: str  # "none" | "confirm" | "danger"
    long_running: bool = False
    positional: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()


COMPONENTS = [
    "ota", "ksu", "suu", "zygisk", "vector",
    "ksu-manager", "suu-manager", "xpad-installer",
    "installer-backup", "boominstaller", "full", "suu-full",
]

_C = CommandSpec
COMMANDS: dict[str, CommandSpec] = {
    "version": _C("version", "Version", True, "none"),
    "status": _C("status", "Status", True, "none", flags=("--json",)),
    "list": _C("list", "List", True, "none"),
    "info": _C("info", "Info", True, "none", positional=("COMPONENT",)),
    "doctor": _C("doctor", "Doctor", True, "none", long_running=True),
    "verify": _C("verify", "Verify", True, "none", positional=("[COMPONENT]",)),
    "root": _C("root", "Root", False, "danger", long_running=True, positional=("[-- COMMAND...]",)),
    "freeze": _C("freeze", "Freeze OTA", False, "confirm", positional=("ota",)),
    "unfreeze": _C("unfreeze", "Unfreeze OTA", False, "confirm", positional=("ota",)),
    "install": _C("install", "Install", False, "danger", long_running=True, positional=("[COMPONENT...]",)),
    "hooks": _C("hooks", "Hooks", False, "danger", long_running=True, positional=("activate|disable",)),
    "repair": _C("repair", "Repair", False, "confirm", long_running=True, positional=("COMPONENT",)),
    "cleanup": _C("cleanup", "Cleanup", False, "confirm", long_running=True),
    "logs": _C("logs", "Logs", True, "none", positional=("export DIRECTORY",)),
    "cache": _C("cache", "Cache", True, "none", positional=("path|list|verify|import|prune|clear",)),
    "update": _C("update", "Update", True, "confirm", long_running=True,
                 flags=("--check", "--version", "--offline", "--reinstall", "--allow-downgrade")),
}


def canonical_id(value: str) -> str:
    return "vector" if value == "lsposed" else value


def shell_quote(value: str) -> str:
    if value and not any(c in value for c in (" ", "\t", "\n", '"', "'")):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_argv(
    command_id: str,
    *,
    positional: list[str] = (),
    flags: list[str] = (),
    serial: str | None = None,
) -> list[str]:
    """Return the device-side argv. serial is ignored here (handled by the adb
    layer); it is accepted so callers pass one uniform shape."""
    _ = serial
    if command_id not in COMMANDS:
        raise ValueError(f"unknown command: {command_id}")
    head = [XPAD2_DEVICE_PATH, command_id]
    return head + list(flags) + list(positional)
