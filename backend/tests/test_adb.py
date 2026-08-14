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
    assert "HOLDER" in result.stdout


def test_run_command_unknown_mock_returns_error(mock_env):
    result = adb.run_command(["__nonexistent__"])
    assert result.exit_code == 1
    assert "unsupported" in result.stderr


def test_run_command_without_mock_uses_real_adb(clean_env, monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        from types import SimpleNamespace
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(adb.subprocess, "run", fake_run)
    adb.run_command(["status", "--json"], serial="abc123")
    assert calls and calls[0][0] == "adb"
    assert "-s" in calls[0] and "abc123" in calls[0]
