"""Remove semantics: ownership, surgical partial removal, idempotence."""

import json
import tomllib

import codex_deepseek_subagent_setup as mod
from conftest import make_args, setup_install


def test_remove_requires_yes(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    assert mod.cmd_remove(make_args(backup_dir=str(backup_root))) == 2
    assert (home / "hooks.json").exists()


def test_remove_full_cycle_idempotent(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    args = make_args(backup_dir=str(backup_root))
    assert mod.cmd_install(args) == 0
    assert mod.cmd_remove(make_args(backup_dir=str(backup_root), yes=True)) == 0
    for rel in mod.MANAGED_FILES:
        assert not (home / rel).exists(), rel
    assert not mod.state_dir(home).exists()
    assert mod.cmd_remove(make_args(backup_dir=str(backup_root), yes=True)) == 0


def test_remove_preserves_unrelated_content(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    # user adds unrelated content to every partial file
    hooks = home / "hooks.json"
    doc = json.loads(hooks.read_text())
    doc["hooks"]["PreToolUse"] = [
        {"matcher": "^Bash$", "hooks": [{"type": "command", "command": "keep", "timeout": 5}]}
    ]
    hooks.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    agents = home / "AGENTS.md"
    agents.write_text(agents.read_text() + "\n# user section\nkeep-me\n", encoding="utf-8")
    config = home / "config.toml"
    config.write_text(config.read_text() + "\n[features]\nuser_thing = true\n", encoding="utf-8")
    # unrelated file in a managed directory
    other_agent = home / "agents" / "other.toml"
    other_agent.write_text('name = "other"\n', encoding="utf-8")

    assert mod.cmd_remove(make_args(backup_dir=str(backup_root), yes=True)) == 0

    remaining = json.loads(hooks.read_text())
    assert "PreToolUse" in remaining["hooks"]
    assert not any(
        g.get("matcher") == "^v4_flash_worker$"
        for g in remaining["hooks"].get("SubagentStart", [])
    )
    text = agents.read_text()
    assert "keep-me" in text
    assert "codex-v4-flash-worker-agents" not in text
    cdata = tomllib.loads(config.read_text())
    assert cdata["features"]["user_thing"] is True
    assert "shell_environment_policy" not in cdata
    assert other_agent.exists()


def test_remove_keeps_drifted_whole_file_then_force(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    skill = home / "skills/use-v4-flash-worker/SKILL.md"
    skill.write_text("user modified", encoding="utf-8")
    assert mod.cmd_remove(make_args(backup_dir=str(backup_root), yes=True)) == 0
    assert skill.exists()
    out = capsys.readouterr().out
    assert "keeping it" in out
    assert mod.cmd_remove(
        make_args(backup_dir=str(backup_root), yes=True, force=True)
    ) == 0
    assert not skill.exists()


def test_remove_prunes_empty_owned_dirs_only(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    sibling = home / "skills" / "other-skill"
    sibling.mkdir(parents=True)
    (sibling / "SKILL.md").write_text("x", encoding="utf-8")
    assert mod.cmd_remove(make_args(backup_dir=str(backup_root), yes=True)) == 0
    assert not (home / "skills/use-v4-flash-worker").exists()
    assert sibling.exists()
    assert not (home / "hooks/codex-deepseek-subagent").exists()
