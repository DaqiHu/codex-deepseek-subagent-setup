"""hooks.json merging: create, preserve unrelated, update, unchanged."""

import json

import codex_deepseek_subagent_setup as mod

HANDOFF = "/some/path/plaintext_handoff.py"


def call(tmp_path, monkeypatch, initial=None):
    monkeypatch.setattr(mod, "is_windows", lambda: False)
    target = tmp_path / "hooks.json"
    if initial is not None:
        target.write_text(json.dumps(initial))
    changed = mod.ensure_hooks_json(tmp_path, HANDOFF, dry_run=False)
    return changed, json.loads(target.read_text())


def test_creates_file(tmp_path, monkeypatch):
    changed, data = call(tmp_path, monkeypatch)
    assert changed
    group = data["hooks"]["SubagentStart"][0]
    assert group["matcher"] == "^v4_flash_worker$"
    cmd = group["hooks"][0]["command"]
    assert cmd.startswith('python3 "') and cmd.endswith(f'"{HANDOFF}" --mode hook')
    assert group["hooks"][0]["timeout"] == 10
    assert group["hooks"][0]["additionalContextLimit"] == 0


def test_preserves_unrelated_hooks(tmp_path, monkeypatch):
    initial = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "^Bash$", "hooks": [{"type": "command", "command": "true", "timeout": 5}]}
            ]
        }
    }
    changed, data = call(tmp_path, monkeypatch, initial)
    assert changed
    assert "PreToolUse" in data["hooks"]
    assert data["hooks"]["PreToolUse"][0]["matcher"] == "^Bash$"
    assert "SubagentStart" in data["hooks"]


def test_unchanged_when_equal(tmp_path, monkeypatch):
    changed, _ = call(tmp_path, monkeypatch)
    assert changed
    changed2, _ = call(tmp_path, monkeypatch)
    assert not changed2


def test_updates_existing_group_once(tmp_path, monkeypatch):
    old_command = 'python3 "/old/path.py" --mode hook'
    initial = {
        "hooks": {
            "SubagentStart": [
                {"matcher": "^v4_flash_worker$", "hooks": [{"type": "command", "command": old_command, "timeout": 10, "additionalContextLimit": 0}]}
            ]
        }
    }
    changed, data = call(tmp_path, monkeypatch, initial)
    assert changed
    groups = data["hooks"]["SubagentStart"]
    assert len(groups) == 1, "must update in place, not duplicate"
    assert HANDOFF in groups[0]["hooks"][0]["command"]
