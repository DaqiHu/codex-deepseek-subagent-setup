"""Cross-platform behavior: Windows hook command, POSIX permissions."""

import json
import os
import stat
import subprocess
import sys

import codex_deepseek_subagent_setup as mod
from conftest import make_args, setup_install

WINDOWS_PYTHON = r"C:\Python 3.14\python.exe"


def test_help_describes_command_windows_field_without_word_joining():
    result = subprocess.run(
        [sys.executable, mod.__file__, "--help"],
        capture_output=True,
        check=True,
        text=True,
    )
    normalized_help = " ".join(result.stdout.split())
    assert "commandWindows field" in normalized_help
    assert "commandWindowsfield" not in normalized_help
    assert "commandWindows field" in mod.MANUAL
    assert "commandWindows with" not in mod.MANUAL


def test_windows_hook_command_and_no_chmod(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path, windows=True)
    backup_root = tmp_path / "backups"
    assert (
        mod.cmd_install(
            make_args(backup_dir=str(backup_root), python_executable=WINDOWS_PYTHON)
        )
        == 0
    )
    hooks = json.loads((home / "hooks.json").read_text())
    group = hooks["hooks"]["SubagentStart"][0]
    assert group["matcher"] == "^v4_flash_worker$"
    handler = group["hooks"][0]
    assert handler["timeout"] == 60
    assert handler["additionalContextLimit"] == 0
    assert handler["command"].startswith("python3 -X utf8")
    assert "-X utf8" in handler["commandWindows"]
    assert WINDOWS_PYTHON in handler["commandWindows"]
    assert "plaintext_handoff.py" in handler["commandWindows"]
    assert "trust" not in json.dumps(hooks).lower()
    if os.name != "nt":
        agent = home / "agents/v4-flash-worker.toml"
        mode = stat.S_IMODE(agent.stat().st_mode)
        assert mode != 0o600


def test_posix_hook_command(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path, windows=False)
    backup_root = tmp_path / "backups"
    assert (
        mod.cmd_install(
            make_args(backup_dir=str(backup_root), python_executable=WINDOWS_PYTHON)
        )
        == 0
    )
    hooks = json.loads((home / "hooks.json").read_text())
    command = hooks["hooks"]["SubagentStart"][0]["hooks"][0]["command"]
    assert command.startswith("python3 -X utf8 ")
    assert "--mode hook" in command


def test_codex_home_with_backslashes(tmp_path, monkeypatch, capsys):
    home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(mod, "resolve_credentials", lambda codex_home: ("u", 'experimental_bearer_token = "t"', "t"))
    monkeypatch.setattr(mod, "is_windows", lambda: False)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    assert (home / "hooks.json").exists()
