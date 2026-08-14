"""Device list parsing and selected-serial memory."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import adb


@dataclass
class Device:
    serial: str
    state: str
    attrs: dict[str, str]


def parse_devices(text: str) -> list[Device]:
    devices: list[Device] = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        attrs: dict[str, str] = {}
        for token in parts[2:]:
            if ":" in token:
                key, value = token.split(":", 1)
                attrs[key] = value
        devices.append(Device(serial=serial, state=state, attrs=attrs))
    return devices


@dataclass
class DeviceMemory:
    selected_serial: str | None = None


def _default_memory_path() -> Path:
    return Path(".xpad2-console-device.json")


def load(path: Path | None = None) -> DeviceMemory:
    path = path or _default_memory_path()
    if not path.exists():
        return DeviceMemory()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return DeviceMemory()
    return DeviceMemory(selected_serial=data.get("selected_serial"))


def save(memory: DeviceMemory, path: Path | None = None) -> None:
    path = path or _default_memory_path()
    path.write_text(
        json.dumps({"selected_serial": memory.selected_serial}),
        encoding="utf-8",
    )
