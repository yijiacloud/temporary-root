import pytest

from app import adb, executor


def test_classify_success_75_needs_reboot():
    assert executor.classify(0) == executor.RunStatus.succeeded
    assert executor.classify(75) == executor.RunStatus.needs_reboot
    assert executor.classify(1) == executor.RunStatus.failed


def test_run_sync_maps_exit_code(mock_env):
    result = executor.run_sync([adb.XPAD2_DEVICE_PATH, "version"], None)
    assert result.status == executor.RunStatus.succeeded
    assert "xpad2" in result.stdout


def test_run_sync_mock_unknown_is_failed(mock_env):
    result = executor.run_sync([adb.XPAD2_DEVICE_PATH, "__nope__"], None)
    assert result.status == executor.RunStatus.failed


@pytest.mark.asyncio
async def test_iter_lines_streams_mock_root(mock_env):
    lines = []
    async for stream, line in executor.iter_lines([adb.XPAD2_DEVICE_PATH, "root"], None):
        lines.append((stream, line))
    assert any("HOLDER" in line for _, line in lines)
