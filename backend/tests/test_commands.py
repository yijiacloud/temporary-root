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
