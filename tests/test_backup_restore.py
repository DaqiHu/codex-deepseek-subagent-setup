"""Backup snapshots: absence-aware manifests, restore semantics."""

import json

import codex_deepseek_subagent_setup as mod
from conftest import make_args, setup_install


def make_home(tmp_path):
    home = tmp_path / "codex-home"
    (home / "agents").mkdir(parents=True)
    (home / "agents" / "v4-flash-worker.toml").write_text("agent=1\n", encoding="utf-8")
    (home / "config.toml").write_text("config=1\n", encoding="utf-8")
    (home / "AGENTS.md").write_text("agents=1\n", encoding="utf-8")
    return home


def test_backup_manifest_is_absence_aware(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    backup = mod.list_backups(backup_root)[0]
    manifest = json.loads((backup / "manifest.json").read_text())
    assert set(manifest["files"]) == set(mod.MANAGED_FILES)
    for entry in manifest["files"].values():
        assert "absent" in entry or "sha256" in entry
    assert manifest["state"]["absent"] is True


def test_backup_captures_original_content(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    (home / "AGENTS.md").write_text("original agents\n", encoding="utf-8")
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    backup = mod.list_backups(backup_root)[0]
    assert (backup / "files" / "AGENTS.md").read_text() == "original agents\n"


def test_restore_recovers_pre_install_state(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    agent = home / "agents" / "v4-flash-worker.toml"
    agent.parent.mkdir(parents=True)
    agent.write_text('name = "v4_flash_worker"\nmodel = "stale"\n', encoding="utf-8")
    (home / "AGENTS.md").write_text("pre agents\n", encoding="utf-8")
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    agent.write_text("garbage", encoding="utf-8")
    (home / "AGENTS.md").write_text("garbage", encoding="utf-8")
    assert (
        mod.cmd_restore(make_args(backup_dir=str(backup_root), restore="latest", yes=True)) == 0
    )
    assert agent.read_text() == 'name = "v4_flash_worker"\nmodel = "stale"\n'
    assert (home / "AGENTS.md").read_text() == "pre agents\n"


def test_restore_deletes_installed_extras(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    assert (
        mod.cmd_restore(make_args(backup_dir=str(backup_root), restore="latest", yes=True)) == 0
    )
    for rel in mod.MANAGED_FILES:
        assert not (home / rel).exists(), rel


def test_restore_refuses_without_yes_when_changed(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    (home / "AGENTS.md").write_text("pre agents\n", encoding="utf-8")
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    (home / "AGENTS.md").write_text("user changed\n", encoding="utf-8")
    assert mod.cmd_restore(make_args(backup_dir=str(backup_root), restore="latest")) == 2
    assert (home / "AGENTS.md").read_text() == "user changed\n"
    assert (
        mod.cmd_restore(
            make_args(backup_dir=str(backup_root), restore="latest", yes=True)
        )
        == 0
    )
    assert (home / "AGENTS.md").read_text() == "pre agents\n"


def test_restore_unknown_id_exits_2(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    assert mod.cmd_restore(make_args(backup_dir=str(backup_root), restore="nope")) == 2


def test_restore_no_backups_exits_1(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_restore(make_args(backup_dir=str(backup_root), restore="latest")) == 1


def test_list_backups_newest_first(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_backup(make_args(backup_dir=str(backup_root))) == 0
    assert mod.cmd_backup(make_args(backup_dir=str(backup_root))) == 0
    backups = mod.list_backups(backup_root)
    assert len(backups) == 2
    assert backups[0].name > backups[1].name
