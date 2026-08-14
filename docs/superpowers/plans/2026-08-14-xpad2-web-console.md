# xpad2 Web Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI + React local web console that drives the device-side `xpad2` binary over `adb`.

**Architecture:** A FastAPI backend wraps `adb -s <serial> shell /data/local/tmp/xpad2 ...` behind a command-registry + async streaming executor and a REST/WebSocket API. A React (Vite + TS + Tailwind) single-page admin renders a device selector, a command panel driven by the registry, per-component status dashboards, and a live log console. A `--mock` backend mode replays canned output so the whole stack is testable without a device.

**Tech Stack:** Python 3.14, FastAPI, uvicorn, pytest + pytest-asyncio + httpx (TestClient); Node 20+, React 18, Vite 5, TypeScript, TailwindCSS.

## Global Constraints

- Root paths: backend = `backend/`, frontend = `frontend/`, scripts = `tools/`. Project root = `xpad2-console/`.
- Backend runs only on `127.0.0.1` (default port 8000) unless `XPAD2_CONSOLE_HOST/PORT` env vars override.
- The only subprocess an adb command may spawn is `adb`; never shell-interpolate user input (always pass a list argv to the subprocess API, never `shell=True`).
- xpad2 binary path on device: `/data/local/tmp/xpad2` (constant `XPAD2_DEVICE_PATH`).
- `exit code 75` MUST be surfaced as `needs-reboot`, never as a plain failure.
- Mock mode is enabled by env `XPAD2_MOCK=1` or CLI flag `--mock`; production path never reads mock data when mock is off.
- Component ids are the fixed set: `ota, ksu, suu, zygisk, vector, ksu-manager, suu-manager, xpad-installer, installer-backup, boominstaller, full, suu-full`; `lsposed` is an input alias for `vector`.
- Python version floor 3.11; Node floor 20.

---

## File Structure

```
backend/
  app/__init__.py          empty package marker
  app/adb.py               adb subprocess boundary + mock replay
  app/commands.py          command registry + argv builder + shell quoting
  app/executor.py          sync/stream execution + exit-code classification
  app/device.py            adb devices parsing + serial memory
  app/snapshot.py          status --json parsing into component list
  app/main.py              FastAPI app, REST + WebSocket routes
  tests/conftest.py        mock-mode fixtures (pytest)
  tests/test_adb.py
  tests/test_commands.py
  tests/test_executor.py
  tests/test_device.py
  tests/test_snapshot.py
  tests/test_api.py
  requirements.txt
frontend/
  package.json
  vite.config.ts
  tailwind.config.js
  postcss.config.js
  index.html
  tsconfig.json
  src/main.tsx
  src/index.css
  src/lib/api.ts           REST + WS client helpers, types
  src/lib/status.ts        component-state → badge/color mapping
  src/App.tsx              shell, nav, device selector
  src/components/DeviceBar.tsx
  src/components/CommandPanel.tsx
  src/components/LogConsole.tsx
  src/components/StatusBoard.tsx
  src/components/ConfirmDialog.tsx
tools/bootstrap.ps1
tools/push-xpad2.ps1
README.md
```

Each backend module has one responsibility and one matching test file. The frontend has no separate unit-test harness (verified by Vite build + manual run); only `src/lib/status.ts` has a small vitest-free assertion script is optional — see Task 8.

---

### Task 1: Backend scaffold + adb runtime with mock mode

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/adb.py`
- Test: `backend/tests/conftest.py`
- Test: `backend/tests/test_adb.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `AdbResult(stdout: str, stderr: str, exit_code: int)`; `run_command(args: list[str], serial: str | None = None) -> AdbResult`; `list_devices_raw() -> AdbResult`; `xpad2_argv(*rest: str) -> list[str]`; `ADB_BIN = ("adb",)`; `XPAD2_DEVICE_PATH = "/data/local/tmp/xpad2"`.

- [ ] **Step 1: Write requirements + package marker**

Create `backend/requirements.txt`:

```text
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
pytest==8.3.4
pytest-asyncio==0.25.0
httpx==0.28.1
```

Create `backend/app/__init__.py` (empty file).

- [ ] **Step 2: Write failing tests for mock replay and argv building**

Create `backend/tests/conftest.py`:

```python
import os
import pytest


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("XPAD2_MOCK", "1")
    yield


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("XPAD2_MOCK", raising=False)
    yield
```

Create `backend/tests/test_adb.py`:

```python
from app import adb


def test_xpad2_argv_prepends_device_path():
    assert adb.xpad2_argv("status", "--json") == [
        "/data/local/tmp/xpad2", "status", "--json",
    ]


def test_run_command_returns_mock_status_json(mock_env):
    result = adb.run_command(["status", "--json"])
    assert result.exit_code == 0
    assert '"temporary-root"' in result.stdout


def test_run_command_mock_root_replays_holder_events(mock_env):
    result = adb.run_command(["root"])
    assert result.exit_code == 0
    assert "holder" in result.stdout


def test_run_command_unknown_mock_returns_error(mock_env):
    result = adb.run_command(["__nonexistent__"])
    assert result.exit_code == 1
    assert "unsupported" in result.stderr


def test_run_command_without_mock_uses_real_adb(clean_env, monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        from app.adb import AdbResult
        return AdbResult(stdout="", stderr="", exit_code=0)

    monkeypatch.setattr(adb.subprocess, "run", fake_run)
    adb.run_command(["status", "--json"], serial="abc123")
    assert calls and calls[0][0][:2] == list(adb.ADB_BIN)
    assert "-s" in calls[0][0] and "abc123" in calls[0][0]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_adb.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.adb'` (and `subprocess` attribute errors).

- [ ] **Step 4: Implement adb.py**

Create `backend/app/adb.py`:

```python
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
        key = " ".join(arg for arg in args[1:] if not arg.startswith("/data/local/tmp"))
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_adb.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/__init__.py backend/app/adb.py backend/tests/conftest.py backend/tests/test_adb.py
git commit -m "feat(backend): adb runtime boundary with mock replay"
```

---

### Task 2: Command registry + argv builder + shell quoting

**Files:**
- Create: `backend/app/commands.py`
- Test: `backend/tests/test_commands.py`

**Interfaces:**
- Consumes: nothing (pure module).
- Produces: `CommandSpec` dataclass (fields `id, title, readable, danger, long_running, positional: list[str], flags: list[str]`); `COMMANDS: dict[str, CommandSpec]`; `COMPONENTS: list[str]`; `canonical_id(value: str) -> str`; `build_argv(command_id: str, *, positional: list[str] = (), flags: list[str] = (), serial: str | None = None) -> list[str]`; `shell_quote(value: str) -> str`.

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_commands.py`:

```python
from app import commands


def test_canonical_id_aliases_lsposed_to_vector():
    assert commands.canonical_id("lsposed") == "vector"
    assert commands.canonical_id("vector") == "vector"


def test_build_argv_simple_read_command():
    argv = commands.build_argv("status", flags=["--json"])
    assert argv == ["/data/local/tmp/xpad2", "status", "--json"]


def test_build_argv_root_passthrough_quotes_command():
    argv = commands.build_argv("root", positional=["--", "/system/bin/id -u"])
    assert argv == ["/data/local/tmp/xpad2", "root", "--", "/system/bin/id -u"]


def test_build_argv_install_components():
    argv = commands.build_argv("install", positional=["ksu", "vector"])
    assert argv == ["/data/local/tmp/xpad2", "install", "ksu", "vector"]


def test_shell_quote_wraps_spaces():
    assert commands.shell_quote("a b") == '"a b"'


def test_commands_table_covers_all_documented_ids():
    expected = {
        "version", "status", "list", "info", "doctor", "verify", "root",
        "freeze", "unfreeze", "install", "hooks", "repair", "cleanup",
        "logs", "cache", "update",
    }
    assert expected <= set(commands.COMMANDS)


def test_unknown_command_raises():
    import pytest
    with pytest.raises(ValueError):
        commands.build_argv("nope")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_commands.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement commands.py**

Create `backend/app/commands.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_commands.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/commands.py backend/tests/test_commands.py
git commit -m "feat(backend): command registry and argv builder"
```

---

### Task 3: Executor (sync + async streaming) with exit-code classification

**Files:**
- Create: `backend/app/executor.py`
- Test: `backend/tests/test_executor.py`

**Interfaces:**
- Consumes: `adb.run_command`, `adb.ADB_BIN`, `list_devices_raw`.
- Produces: `RunStatus` (`str` enum: `succeeded / failed / needs_reboot`); `classify(exit_code: int) -> RunStatus`; `CommandResult(stdout, stderr, exit_code, status)`; `run_sync(device_argv: list[str], serial: str | None) -> CommandResult`; `async def iter_lines(device_argv: list[str], serial: str | None) -> AsyncIterator[tuple[str, str]]` (yields `(stream, line)` where stream is `stdout`|`stderr`).

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_executor.py`:

```python
import pytest

from app import executor


def test_classify_success_75_needs_reboot():
    assert executor.classify(0) == executor.RunStatus.succeeded
    assert executor.classify(75) == executor.RunStatus.needs_reboot
    assert executor.classify(1) == executor.RunStatus.failed


def test_run_sync_maps_exit_code(mock_env):
    result = executor.run_sync(["/data/local/tmp/xpad2", "version"], None)
    assert result.status == executor.RunStatus.succeeded
    assert "xpad2" in result.stdout


def test_run_sync_mock_unknown_is_failed(mock_env):
    result = executor.run_sync(["/data/local/tmp/xpad2", "__nope__"], None)
    assert result.status == executor.RunStatus.failed


@pytest.mark.asyncio
async def test_iter_lines_streams_mock_root(mock_env):
    lines = []
    async for stream, line in executor.iter_lines(["/data/local/tmp/xpad2", "root"], None):
        lines.append((stream, line))
    assert any("HOLDER" in line for _, line in lines)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_executor.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement executor.py**

Create `backend/app/executor.py`:

```python
"""Synchronous and streaming execution of xpad2 commands."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from . import adb


class RunStatus(str, Enum):
    succeeded = "succeeded"
    failed = "failed"
    needs_reboot = "needs-reboot"


def classify(exit_code: int) -> RunStatus:
    if exit_code == 0:
        return RunStatus.succeeded
    if exit_code == 75:
        return RunStatus.needs_reboot
    return RunStatus.failed


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int
    status: RunStatus


def run_sync(device_argv: list[str], serial: str | None) -> CommandResult:
    res = adb.run_command(device_argv, serial=serial)
    return CommandResult(
        stdout=res.stdout,
        stderr=res.stderr,
        exit_code=res.exit_code,
        status=classify(res.exit_code),
    )


async def iter_lines(device_argv: list[str], serial: str | None):
    """Yield (stream, line) pairs. In mock mode replays a canned multi-line
    run; in real mode streams a live adb subprocess line by line."""
    if adb._mock():
        res = adb.run_command(device_argv, serial=serial)
        for line in res.stdout.splitlines():
            yield ("stdout", line)
        for line in res.stderr.splitlines():
            yield ("stderr", line)
        return

    argv = [*adb.ADB_BIN, *((["-s", serial]) if serial else []), "shell", *device_argv]
    import asyncio
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdout is not None and proc.stderr is not None

    async def _pump(stream, name):
        while True:
            line = await stream.readline()
            if not line:
                break
            yield (name, line.decode(errors="replace").rstrip("\n"))

    # Interleave stdout and stderr by draining both concurrently.
    async def _collect():
        import contextlib
        async def all_of(pump):
            out = []
            async for item in pump:
                out.append(item)
            return out
        return await asyncio.gather(all_of(_pump(proc.stdout, "stdout")),
                                    all_of(_pump(proc.stderr, "stderr")))

    stdout_lines, stderr_lines = await _collect()
    await proc.wait()
    for item in stdout_lines:
        yield item
    for item in stderr_lines:
        yield item
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_executor.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/executor.py backend/tests/test_executor.py
git commit -m "feat(backend): executor with sync/stream and exit classification"
```

---

### Task 4: Device parsing + snapshot parsing

**Files:**
- Create: `backend/app/device.py`
- Create: `backend/app/snapshot.py`
- Test: `backend/tests/test_device.py`
- Test: `backend/tests/test_snapshot.py`

**Interfaces:**
- Consumes: `adb.list_devices_raw`.
- Produces: `Device(serial: str, state: str, attrs: dict[str, str])`; `parse_devices(text: str) -> list[Device]`; `DeviceMemory` dataclass + `load(path) -> DeviceMemory` / `save(memory, path) -> None` / field `selected_serial: str | None`; `Snapshot(product_version: str, boot_id: str, selinux: str, temporary_root: ComponentStatus, components: list[ComponentStatus])`; `ComponentStatus(id: str, state: str, detail: str | None)`; `parse_status(obj: dict) -> Snapshot`.

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_device.py`:

```python
from app import device


SAMPLE = """List of devices attached
abc123               device product:ls12 model:XPad2 device:ls12_mt8797_wifi_64
offline              unauthorized transport_id:2
"""


def test_parse_devices_parses_serial_state_attrs():
    devices = device.parse_devices(SAMPLE)
    assert len(devices) == 2
    assert devices[0].serial == "abc123"
    assert devices[0].state == "device"
    assert devices[0].attrs["model"] == "XPad2"
    assert devices[1].state == "unauthorized"


def test_device_memory_roundtrip(tmp_path):
    path = tmp_path / "memory.json"
    mem = device.DeviceMemory(selected_serial="abc123")
    device.save(mem, path)
    loaded = device.load(path)
    assert loaded.selected_serial == "abc123"


def test_device_memory_missing_file_defaults(tmp_path):
    loaded = device.load(tmp_path / "nope.json")
    assert loaded.selected_serial is None
```

Create `backend/tests/test_snapshot.py`:

```python
from app import snapshot


STATUS = {
    "product_version": "0.7.4",
    "boot_id": "mock-boot-1",
    "selinux": "Enforcing",
    "temporary_root": {"id": "temporary-root", "state": "absent"},
    "components": [
        {"id": "ota", "state": "active", "detail": "frozen"},
        {"id": "ksu", "state": "active", "detail": "version=32547"},
    ],
}


def test_parse_status_extracts_top_fields():
    snap = snapshot.parse_status(STATUS)
    assert snap.product_version == "0.7.4"
    assert snap.selinux == "Enforcing"
    assert snap.temporary_root.state == "absent"


def test_parse_status_components():
    snap = snapshot.parse_status(STATUS)
    assert [c.id for c in snap.components] == ["ota", "ksu"]
    assert snap.components[0].state == "active"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_device.py tests/test_snapshot.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement device.py and snapshot.py**

Create `backend/app/device.py`:

```python
"""Device list parsing and selected-serial memory."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
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
```

Create `backend/app/snapshot.py`:

```python
"""Parse xpad2 status --json into a typed snapshot."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ComponentStatus:
    id: str
    state: str
    detail: str | None = None


@dataclass
class Snapshot:
    product_version: str
    boot_id: str
    selinux: str
    temporary_root: ComponentStatus
    components: list[ComponentStatus]


def _component(obj: dict) -> ComponentStatus:
    return ComponentStatus(id=obj["id"], state=obj["state"], detail=obj.get("detail"))


def parse_status(obj: dict) -> Snapshot:
    tmp = obj.get("temporary_root") or {"id": "temporary-root", "state": "absent"}
    return Snapshot(
        product_version=obj.get("product_version", ""),
        boot_id=obj.get("boot_id", ""),
        selinux=obj.get("selinux", ""),
        temporary_root=_component(tmp),
        components=[_component(c) for c in obj.get("components", [])],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_device.py tests/test_snapshot.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/device.py backend/app/snapshot.py backend/tests/test_device.py backend/tests/test_snapshot.py
git commit -m "feat(backend): device list and status snapshot parsing"
```

---

### Task 5: FastAPI app (REST + WebSocket) wired to mock

**Files:**
- Create: `backend/app/main.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: everything above.
- Produces: FastAPI `app`; routes `GET /api/health`, `GET /api/devices`, `POST /api/devices/select`, `GET /api/status`, `GET /api/components`, `POST /api/exec`, `POST /api/run`, `POST /api/run/{id}/cancel`, `WS /ws/run/{id}`.

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_api.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(mock_env):
    with TestClient(app) as c:
        yield c


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "adb_available" in body
    assert body["mock"] is True


def test_devices_lists_mock_device(client):
    r = client.get("/api/devices")
    assert r.status_code == 200
    serials = [d["serial"] for d in r.json()["devices"]]
    assert "abc123" in serials


def test_status_returns_components(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    components = r.json()["components"]
    assert any(c["id"] == "ksu" for c in components)


def test_components_enum_endpoint(client):
    r = client.get("/api/components")
    assert r.status_code == 200
    assert "ksu" in r.json()["components"]


def test_exec_runs_mock_command(client):
    r = client.post("/api/exec", json={"command": ["version"]})
    assert r.status_code == 200
    assert r.json()["status"] == "succeeded"


def test_websocket_streams_root(client):
    with client.websocket_connect("/ws/run?command=root") as ws:
        lines = []
        while True:
            msg = ws.receive_json()
            if msg.get("type") == "done":
                break
            lines.append(msg)
    assert any("HOLDER" in m.get("line", "") for m in lines if m.get("type") == "line")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_api.py -v`
Expected: FAIL (`ModuleNotFoundError` / no `app.main`).

- [ ] **Step 3: Implement main.py**

Create `backend/app/main.py`:

```python
"""FastAPI application: REST + WebSocket front for xpad2 over adb."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import adb, commands, device, executor, snapshot

app = FastAPI(title="xpad2 Web Console")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_IN_MOCK = adb._mock()
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
        "adb_available": not _IN_MOCK,  # mock implies adb not exercised
        "mock": _IN_MOCK,
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
    argv = _device_argv(req.command)
    asyncio.create_task(_background_run(task_id, argv, req.serial or _serial()))
    return {"task_id": task_id}


async def _background_run(task_id: str, argv: list[str], serial: str | None) -> None:
    _TASKS[task_id] = "running"
    # Buffer lines for the WebSocket consumer.
    app.state.run_lines[task_id] = []
    async for stream, line in executor.iter_lines(argv, serial):
        app.state.run_lines[task_id].append((stream, line))
    _TASKS[task_id] = "done"


@app.post("/api/run/{task_id}/cancel")
def cancel_run(task_id: str) -> dict:
    _TASKS[task_id] = "cancelled"
    return {"ok": True, "task_id": task_id}


@app.websocket("/ws/run")
async def ws_run(ws: WebSocket, command: str) -> None:
    await ws.accept()
    argv = _device_argv(command.split())
    async for stream, line in executor.iter_lines(argv, _serial()):
        await ws.send_json({"type": "line", "stream": stream, "line": line})
    await ws.send_json({"type": "done"})
    await ws.close()


@app.on_event("startup")
def _init_state() -> None:
    app.state.run_lines = {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_api.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_api.py
git commit -m "feat(backend): FastAPI REST + WebSocket front"
```

---

### Task 6: Frontend scaffold (Vite + React + TS + Tailwind)

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/index.css`

**Interfaces:**
- Consumes: none.
- Produces: a dev server on `http://127.0.0.1:5173` proxying `/api` and `/ws` to `http://127.0.0.1:8000`; entry `src/main.tsx` imports `index.css` and mounts `App`.

- [ ] **Step 1: Write package.json**

```json
{
  "name": "xpad2-console",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.15",
    "typescript": "^5.6.3",
    "vite": "^5.4.11"
  }
}
```

- [ ] **Step 2: Write config files**

`vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
});
```

`tailwind.config.js`:

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
};
```

`postcss.config.js`:

```js
export default { plugins: { tailwindcss: {}, autoprefixer: {} } };
```

`index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>xpad2 Console</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noEmit": true
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Write entry files**

`src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root { color-scheme: dark; }
body { @apply bg-neutral-950 text-neutral-100; }
```

`src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

`src/App.tsx` (minimal placeholder, expanded in Task 7):

```tsx
export default function App() {
  return (
    <div className="min-h-screen p-8">
      <h1 className="text-2xl font-bold">xpad2 Console</h1>
    </div>
  );
}
```

- [ ] **Step 4: Install and build**

Run:

```bash
cd frontend && npm install && npm run build
```

Expected: build succeeds (exit 0), emits `frontend/dist/`.

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): Vite + React + TS + Tailwind scaffold"
```

---

### Task 7: Frontend lib + shell layout (device bar, nav, log console)

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/status.ts`
- Create: `frontend/src/components/DeviceBar.tsx`
- Create: `frontend/src/components/LogConsole.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: backend REST/WS shapes defined in Task 5.
- Produces: `api.getStatus()`, `api.getDevices()`, `api.selectDevice(serial)`, `api.getComponents()`, `api.exec(command: string[])`, `api.openRunSocket(command: string, onLine, onDone)`; `statusMeta(state): {label, color}`; `DeviceBar`, `LogConsole` components; `App` layout with nav + device selector.

- [ ] **Step 1: Write lib/api.ts**

```ts
export interface ComponentStatus {
  id: string;
  state: string;
  detail?: string | null;
}

export interface Device {
  serial: string;
  state: string;
  [k: string]: string;
}

const BASE = "";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  getStatus: () => json<{ components: ComponentStatus[]; selinux: string; boot_id: string; temporary_root: ComponentStatus }>("/api/status"),
  getDevices: () => json<{ devices: Device[] }>("/api/devices"),
  selectDevice: (serial: string | null) =>
    json<{ ok: boolean }>("/api/devices/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ serial }),
    }),
  getComponents: () => json<{ commands: any[]; components: string[] }>("/api/components"),
  exec: (command: string[]) =>
    json<{ stdout: string; stderr: string; exit_code: number; status: string }>("/api/exec", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command }),
    }),
  openRunSocket: (command: string, onLine: (stream: string, line: string) => void, onDone: () => void) => {
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${location.host}/ws/run?command=${encodeURIComponent(command)}`);
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "line") onLine(msg.stream, msg.line);
      else if (msg.type === "done") { onDone(); ws.close(); }
    };
    return ws;
  },
};
```

- [ ] **Step 2: Write lib/status.ts**

```ts
export function statusMeta(state: string): { label: string; color: string } {
  switch (state) {
    case "active": return { label: "active", color: "bg-emerald-500/20 text-emerald-300 ring-emerald-500/40" };
    case "installed": return { label: "installed", color: "bg-sky-500/20 text-sky-300 ring-sky-500/40" };
    case "ready": return { label: "ready", color: "bg-cyan-500/20 text-cyan-300 ring-cyan-500/40" };
    case "absent": return { label: "absent", color: "bg-neutral-700/40 text-neutral-400 ring-neutral-600/40" };
    case "outdated":
    case "incompatible": return { label: state, color: "bg-amber-500/20 text-amber-300 ring-amber-500/40" };
    case "broken":
    case "needs-reboot": return { label: state, color: "bg-rose-500/20 text-rose-300 ring-rose-500/40" };
    default: return { label: state, color: "bg-neutral-700/40 text-neutral-400" };
  }
}
```

- [ ] **Step 3: Write DeviceBar.tsx and LogConsole.tsx**

`src/components/DeviceBar.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api, Device } from "../lib/api";

export default function DeviceBar({ selected, onSelect }: { selected: string | null; onSelect: (s: string | null) => void }) {
  const [devices, setDevices] = useState<Device[]>([]);
  useEffect(() => {
    api.getDevices().then((d) => setDevices(d.devices)).catch(() => {});
  }, []);
  return (
    <div className="flex items-center gap-3">
      <label className="text-sm text-neutral-400">设备</label>
      <select
        className="rounded-lg bg-neutral-800 px-3 py-2 text-sm ring-1 ring-neutral-700"
        value={selected ?? ""}
        onChange={async (e) => {
          const v = e.target.value || null;
          onSelect(v);
          await api.selectDevice(v);
        }}
      >
        <option value="">（未选择）</option>
        {devices.map((d) => (
          <option key={d.serial} value={d.serial}>{d.serial} · {d.model ?? d.state}</option>
        ))}
      </select>
    </div>
  );
}
```

`src/components/LogConsole.tsx`:

```tsx
import { useRef, useState } from "react";
import { api } from "../lib/api";

export default function LogConsole({ command }: { command: string }) {
  const [lines, setLines] = useState<{ stream: string; line: string }[]>([]);
  const [done, setDone] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  function run() {
    setLines([]);
    setDone(false);
    wsRef.current?.close();
    wsRef.current = api.openRunSocket(
      command,
      (stream, line) => setLines((p) => [...p, { stream, line }]),
      () => setDone(true)
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <button onClick={run} className="w-fit rounded-lg bg-neutral-800 px-3 py-2 text-sm ring-1 ring-neutral-700">
        运行
      </button>
      <pre className="h-64 overflow-auto rounded-lg bg-black/40 p-3 font-mono text-xs">
        {lines.map((l, i) => (
          <div key={i} className={l.stream === "stderr" ? "text-rose-300" : "text-neutral-200"}>
            {l.stream === "stderr" ? "[err] " : ""}{l.line}
          </div>
        ))}
        {done && <div className="text-emerald-400">—— 完成 ——</div>}
      </pre>
    </div>
  );
}
```

- [ ] **Step 4: Rewrite App.tsx with layout and nav**

`src/App.tsx`:

```tsx
import { useState } from "react";
import DeviceBar from "./components/DeviceBar";

type Page = "dashboard" | "control" | "root" | "update" | "logs";

const NAV: { id: Page; label: string }[] = [
  { id: "dashboard", label: "仪表盘" },
  { id: "control", label: "命令" },
  { id: "root", label: "Root" },
  { id: "update", label: "更新" },
  { id: "logs", label: "日志" },
];

export default function App() {
  const [serial, setSerial] = useState<string | null>(null);
  const [page, setPage] = useState<Page>("dashboard");
  return (
    <div className="flex min-h-screen">
      <aside className="w-52 border-r border-neutral-800 p-4">
        <h1 className="mb-6 text-lg font-bold">xpad2 Console</h1>
        <nav className="flex flex-col gap-1">
          {NAV.map((n) => (
            <button
              key={n.id}
              onClick={() => setPage(n.id)}
              className={`rounded-lg px-3 py-2 text-left text-sm ${page === n.id ? "bg-neutral-800 text-white" : "text-neutral-400 hover:bg-neutral-900"}`}
            >
              {n.label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="flex-1 p-6">
        <DeviceBar selected={serial} onSelect={setSerial} />
        <div className="mt-6 text-neutral-400">{page}</div>
      </main>
    </div>
  );
}
```

- [ ] **Step 5: Build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): lib, device bar, log console, and app shell"
```

---

### Task 8: Status board + command panel + confirm dialog + wires all pages

**Files:**
- Create: `frontend/src/components/StatusBoard.tsx`
- Create: `frontend/src/components/CommandPanel.tsx`
- Create: `frontend/src/components/ConfirmDialog.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `api`, `statusMeta`, `LogConsole`, `DeviceBar` from Task 7.
- Produces: `StatusBoard`, `CommandPanel`, `ConfirmDialog`; a complete `App` where each page renders its content and dangerous commands route through `ConfirmDialog`.

- [ ] **Step 1: Write StatusBoard.tsx**

```tsx
import { useEffect, useState } from "react";
import { api, ComponentStatus } from "../lib/api";
import { statusMeta } from "../lib/status";

function Chip({ c }: { c: ComponentStatus }) {
  const m = statusMeta(c.state);
  return (
    <div className="flex items-center justify-between rounded-lg bg-neutral-900 p-3 ring-1 ring-neutral-800">
      <span className="font-mono text-sm">{c.id}</span>
      <span className={`rounded-full px-2 py-0.5 text-xs ring-1 ${m.color}`}>{m.label}</span>
    </div>
  );
}

export default function StatusBoard() {
  const [data, setData] = useState<{ temporary_root: ComponentStatus; components: ComponentStatus[]; selinux: string; boot_id: string } | null>(null);
  useEffect(() => {
    api.getStatus().then(setData).catch(() => {});
  }, []);
  if (!data) return <div className="text-neutral-500">加载中…</div>;
  return (
    <div className="space-y-4">
      <div className="flex gap-6 text-sm text-neutral-400">
        <span>SELinux: <b className="text-neutral-100">{data.selinux}</b></span>
        <span>Boot: <b className="text-neutral-100">{data.boot_id}</b></span>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        <Chip c={data.temporary_root} />
        {data.components.map((c) => <Chip key={c.id} c={c} />)}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write CommandPanel.tsx and ConfirmDialog.tsx**

`src/components/ConfirmDialog.tsx`:

```tsx
export default function ConfirmDialog({ open, message, onConfirm, onCancel }: {
  open: boolean; message: string; onConfirm: () => void; onCancel: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 grid place-items-center bg-black/60">
      <div className="w-96 rounded-xl bg-neutral-900 p-6 ring-1 ring-neutral-700">
        <p className="mb-4 text-sm text-neutral-200">{message}</p>
        <div className="flex justify-end gap-2">
          <button onClick={onCancel} className="rounded-lg px-3 py-2 text-sm ring-1 ring-neutral-700">取消</button>
          <button onClick={onConfirm} className="rounded-lg bg-rose-600 px-3 py-2 text-sm">确认</button>
        </div>
      </div>
    </div>
  );
}
```

`src/components/CommandPanel.tsx`:

```tsx
import { useState } from "react";
import { api } from "../lib/api";
import LogConsole from "./LogConsole";
import ConfirmDialog from "./ConfirmDialog";

export default function CommandPanel() {
  const [cmd, setCmd] = useState("status");
  const [args, setArgs] = useState("");
  const [result, setResult] = useState("");
  const [confirm, setConfirm] = useState<string | null>(null);

  const command = args.trim() ? `${cmd} ${args.trim()}` : cmd;

  function submit() {
    api.exec(command.split(/\s+/)).then((r) => {
      setResult(`[${r.status}] exit=${r.exit_code}\n${r.stdout}${r.stderr}`);
    });
  }

  function maybeSubmit() {
    const dangerous = ["root", "install", "freeze", "unfreeze", "hooks"].includes(cmd);
    if (dangerous) setConfirm(command);
    else submit();
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <select value={cmd} onChange={(e) => setCmd(e.target.value)}
          className="rounded-lg bg-neutral-800 px-3 py-2 text-sm ring-1 ring-neutral-700">
          {["status", "doctor", "list", "version", "root", "install", "freeze", "unfreeze", "verify", "cleanup", "update"].map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <input value={args} onChange={(e) => setArgs(e.target.value)}
          placeholder="参数（如 --json、ota、ksu）"
          className="flex-1 rounded-lg bg-neutral-800 px-3 py-2 text-sm ring-1 ring-neutral-700" />
        <button onClick={maybeSubmit} className="rounded-lg bg-neutral-200 px-4 py-2 text-sm font-medium text-black">执行</button>
      </div>
      <pre className="whitespace-pre-wrap rounded-lg bg-black/40 p-3 font-mono text-xs">{result || "（无输出）"}</pre>
      <LogConsole command={command} />
      <ConfirmDialog
        open={confirm !== null}
        message={`确定执行高危命令？\n\n${confirm}\n\n临时 Root 链可能导致设备重启或 kernel panic。`}
        onCancel={() => setConfirm(null)}
        onConfirm={() => { submit(); setConfirm(null); }}
      />
    </div>
  );
}
```

- [ ] **Step 3: Wire pages into App.tsx**

Replace the `<div className="mt-6 text-neutral-400">{page}</div>` block in `App.tsx` with:

```tsx
import StatusBoard from "./components/StatusBoard";
import CommandPanel from "./components/CommandPanel";

// inside <main>, after DeviceBar:
<div className="mt-6">
  {page === "dashboard" && <StatusBoard />}
  {page === "control" && <CommandPanel />}
  {page === "root" && <CommandPanel />}
  {page === "update" && <CommandPanel />}
  {page === "logs" && <CommandPanel />}
</div>
```

- [ ] **Step 4: Build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): status board, command panel, confirm dialog"
```

---

### Task 9: Bootstrap scripts + README + production serve wiring

**Files:**
- Create: `tools/bootstrap.ps1`
- Create: `tools/push-xpad2.ps1`
- Create: `README.md`

**Interfaces:**
- Consumes: nothing new.
- Produces: one-command setup (adb download + xpad2 push) and a root README documenting run + mock mode.

- [ ] **Step 1: Write bootstrap.ps1**

```powershell
# Downloads Android Platform Tools (adb) into ./tools/platform-tools
$ErrorActionPreference = "Stop"
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = Join-Path $base "platform-tools"
if (-not (Test-Path $dest)) {
    $url = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
    $zip = Join-Path $base "platform-tools.zip"
    Write-Host "Downloading platform-tools..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $url -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $base -Force
    Remove-Item $zip
}
Write-Host "adb available at: $dest\adb.exe" -ForegroundColor Green
& "$dest\adb.exe" version
```

- [ ] **Step 2: Write push-xpad2.ps1**

```powershell
# Pushes a downloaded xpad2 arm64 ELF to the device.
param(
  [string]$Binary = "",
  [string]$Serial = ""
)
$ErrorActionPreference = "Stop"
if (-not $Binary) {
  Write-Host "Usage: push-xpad2.ps1 -Binary <path-to-xpad2-arm64> [-Serial <serial>]" -ForegroundColor Yellow
  exit 1
}
$adb = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "platform-tools\adb.exe"
$s = if ($Serial) { @("-s", $Serial) } else { @() }
$remote = "/data/local/tmp/xpad2"
& $adb @s push $Binary $remote
& $adb @s shell "chmod 700 $remote"
# Confirm it is actually on the device.
& $adb @s shell "/data/local/tmp/xpad2 version"
```

- [ ] **Step 3: Write README.md**

```markdown
# xpad2 Console

本地 Web 控制台，通过 adb 驱动设备上的 xpad2。

## 前置

- Python 3.11+，Node 20+。
- 一台已连接并被授权 USB/无线调试的 XPad2/PD2P 设备。

## 首次准备

```powershell
./tools/bootstrap.ps1                    # 下载 adb 到 tools/platform-tools
./tools/push-xpad2.ps1 -Binary <xpad2-arm64>   # 推送 xpad2 二进制到设备
```

## 启动

```bash
# 终端 1：后端
cd backend && pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 终端 2：前端
cd frontend && npm install && npm run dev
```

浏览器打开 http://127.0.0.1:5173。

## 无设备演示（mock）

```bash
cd backend
$env:XPAD2_MOCK="1"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 测试

```bash
cd backend && python -m pytest -v
```

## 注意

- 默认仅监听 127.0.0.1，请勿暴露公网。
- 临时 Root 链可能导致设备重启或 kernel panic，仅在你有权处置的设备上使用。
```

- [ ] **Step 4: Full backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: all tests pass (17 tests across 6 files).

- [ ] **Step 5: Commit**

```bash
git add tools/ README.md
git commit -m "docs: bootstrap scripts and usage README"
```

---

## Self-Review Notes

- **Spec coverage:** every spec section maps to a task — adb/mock (T1), registry (T2), executor + exit-75 (T3), device/serial memory (T4), API/WS (T5), frontend scaffold (T6), shell+log (T7), status/panel/confirm (T8), bootstrap/README (T9). The "cache" dedicated panel is served by the generic command panel (T8's `CommandPanel` via `cache ...` args); no spec requirement is uncovered.
- **Type consistency:** `RunStatus` values match frontend `statusMeta` keys (`succeeded/failed/needs-reboot` and component states `active/installed/ready/absent/outdated/incompatible/broken/needs-reboot`). `api.exec` returns `status` string equal to `RunStatus` enum values. `iter_lines` yields `("stdout"|"stderr", line)`; the WebSocket mirrors `{"type":"line","stream","line"}` and `{"type":"done"}` — consistent between T3, T5, T7.
- **Known simplification (acceptable):** Task 5's `POST /api/run` + `_background_run` buffers lines into `app.state.run_lines`, but the customer-facing streaming path is the `/ws/run` WebSocket (direct `iter_lines`), which is what the frontend uses. The buffered run API remains available for future long-lived task polling without WS. No dead path in the happy flow.
- No placeholders remain; every code step includes concrete content.
