"""Hook group merge and the installed Hook definition shape."""

import json

import codex_deepseek_subagent_setup as mod


def replacement():
    return {
        "matcher": "^v4_flash_worker$",
        "hooks": [{"type": "command", "command": "python3 -X utf8 /x --mode hook", "timeout": 60}],
    }


def test_merge_hooks_creates_document():
    doc, changed, previous = mod.merge_hooks(None, replacement())
    assert changed is True
    assert previous is None
    assert doc["hooks"]["SubagentStart"] == [replacement()]


def test_merge_hooks_preserves_unrelated_groups():
    existing = {"hooks": {"PreToolUse": [{"matcher": "^Bash$", "hooks": []}]}}
    doc, changed, _ = mod.merge_hooks(existing, replacement())
    assert changed is True
    assert doc["hooks"]["PreToolUse"] == existing["hooks"]["PreToolUse"]


def test_merge_hooks_updates_in_place_no_duplicate():
    old = {"matcher": "^v4_flash_worker$", "hooks": [{"type": "command", "command": "old"}]}
    existing = {"hooks": {"SubagentStart": [old]}}
    doc, changed, previous = mod.merge_hooks(existing, replacement())
    assert len(doc["hooks"]["SubagentStart"]) == 1
    assert changed is True
    assert previous == old


def test_merge_hooks_unchanged():
    existing = {"hooks": {"SubagentStart": [replacement()]}}
    doc, changed, previous = mod.merge_hooks(existing, replacement())
    assert changed is False
    assert previous == replacement()


def test_hook_replacement_group_shape(tmp_path):
    codex_home = tmp_path / "home"
    group = mod.hook_replacement_group(codex_home, r"C:\Python 3.14\python.exe")
    assert group["matcher"] == "^v4_flash_worker$"
    handler = group["hooks"][0]
    assert handler["type"] == "command"
    assert handler["timeout"] == 60
    assert handler["additionalContextLimit"] == 0
    assert handler["command"].startswith("python3 -X utf8")
    assert "plaintext_handoff.py" in handler["command"]
    assert "-X utf8" in handler["commandWindows"]
    assert r"C:\Python 3.14\python.exe" in handler["commandWindows"]


def test_installed_hook_has_no_trust_hash(tmp_path, monkeypatch, capsys):
    from conftest import make_args, setup_install

    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    hooks = json.loads((home / "hooks.json").read_text())
    assert "trust" not in json.dumps(hooks).lower()


def test_hook_definition_changed_reported(tmp_path, monkeypatch, capsys):
    from conftest import make_args, setup_install

    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    args = make_args(backup_dir=str(backup_root))
    assert mod.cmd_install(args) == 0
    out = capsys.readouterr().out
    assert "hook definition changed" in out
    # second run: unchanged, no review needed
    assert mod.cmd_install(args) == 0
    out = capsys.readouterr().out
    assert "no new trust review needed" in out
