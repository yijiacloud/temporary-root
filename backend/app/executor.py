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
    """Yield (stream, line) pairs live as they arrive. In mock mode replays a
    canned multi-line run; in real mode streams an adb subprocess line-by-line
    without waiting for it to finish."""
    if adb._mock():
        res = adb.run_command(device_argv, serial=serial)
        for line in res.stdout.splitlines():
            yield ("stdout", line)
        for line in res.stderr.splitlines():
            yield ("stderr", line)
        return

    import asyncio

    argv = [*adb.ADB_BIN, *((["-s", serial]) if serial else []), "shell", *device_argv]
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdout is not None and proc.stderr is not None

    queue: asyncio.Queue = asyncio.Queue()

    async def pump(stream, name):
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode(errors="replace").rstrip("\r\n")
                if text:
                    await queue.put((name, text))
        except asyncio.CancelledError:
            pass

    readers = asyncio.gather(pump(proc.stdout, "stdout"), pump(proc.stderr, "stderr"))

    while True:
        done = readers.done()
        if not queue.empty():
            yield await queue.get()
            continue
        if done:
            break
        # wait for the next line (or a short tick to re-check reader status)
        try:
            yield await asyncio.wait_for(queue.get(), timeout=0.25)
        except asyncio.TimeoutError:
            continue

    await proc.wait()
