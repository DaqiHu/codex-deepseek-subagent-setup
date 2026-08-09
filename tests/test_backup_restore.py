"""Backup creation and restore."""

import json

import codex_deepseek_subagent_setup as mod

MANAGED = [
    "agents/v4-flash-worker.toml",
    "config.toml",
    "AGENTS.md",
]


def make_home(tmp_path):
    home = tmp_path / "codex-home"
    (home / "agents").mkdir(parents=True)
    (home / "agents" / "v4-flash-worker.toml").write_text("agent=1\n")
    (home / "config.toml").write_text("config=1\n")
    (home / "AGENTS.md").write_text("agents=1\n")
    return home


def test_backup_snapshot(tmp_path):
    home = make_home(tmp_path)
    backup_root = tmp_path / "backups"
    backup_dir = mod.create_backup(home, backup_root)
    manifest = json.loads((backup_dir / "manifest.json").read_text())
    assert set(manifest["files"]) == set(MANAGED)
    assert (backup_dir / "files" / "agents" / "v4-flash-worker.toml").exists()
    assert (backup_dir / "files" / "config.toml").read_text() == "config=1\n"


def test_restore_recovers_poisoned_file(tmp_path):
    home = make_home(tmp_path)
    backup_root = tmp_path / "backups"
    mod.create_backup(home, backup_root)
    (home / "config.toml").write_text("POISONED")
    assert mod.restore_backup(mod.list_backups(backup_root)[0], home)
    assert (home / "config.toml").read_text() == "config=1\n"


def test_list_backups_newest_first(tmp_path):
    home = make_home(tmp_path)
    backup_root = tmp_path / "backups"
    first = mod.create_backup(home, backup_root)
    second = mod.create_backup(home, backup_root)
    backups = mod.list_backups(backup_root)
    assert backups[0] == second and backups[1] == first
