"""End-to-end install -> backup -> poison -> restore -> status -> remove."""

import tomllib

import codex_deepseek_subagent_setup as mod
from conftest import make_args, setup_install


def test_full_cycle(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    (home / "agents").mkdir(parents=True)
    (home / "agents" / "v4-flash-worker.toml").write_text(
        'name = "v4_flash_worker"\nmodel = "stale"\n', encoding="utf-8"
    )
    (home / "AGENTS.md").write_text("original agents\n", encoding="utf-8")

    # install/upsert creates a pre-change backup
    args = make_args(backup_dir=str(backup_root))
    assert mod.cmd_install(args) == 0
    backups = mod.list_backups(backup_root)
    assert len(backups) == 1
    data = tomllib.loads((home / "agents/v4-flash-worker.toml").read_text())
    assert data["model"] == "deepseek-v4-flash"
    assert data["sandbox_mode"] == "danger-full-access"

    # idempotent second run: no changes, no new backup
    assert mod.cmd_install(args) == 0
    out = capsys.readouterr().out
    assert "0 file(s) changed" in out
    assert len(mod.list_backups(backup_root)) == 1

    # poison + restore: the pre-change snapshot restores the original content
    (home / "agents/v4-flash-worker.toml").write_text("garbage", encoding="utf-8")
    (home / "AGENTS.md").write_text("garbage", encoding="utf-8")
    assert (
        mod.cmd_restore(
            make_args(backup_dir=str(backup_root), restore="latest", yes=True)
        )
        == 0
    )
    assert (home / "agents/v4-flash-worker.toml").read_text() == (
        'name = "v4_flash_worker"\nmodel = "stale"\n'
    )
    assert (home / "AGENTS.md").read_text() == "original agents\n"

    # status then remove: the pre-install files were restored, so they are no
    # longer installer-owned and remove keeps them; installer-created artifacts
    # are gone.
    assert mod.cmd_status(make_args(backup_dir=str(backup_root))) == 0
    assert mod.cmd_remove(make_args(backup_dir=str(backup_root), yes=True)) == 0
    assert (home / "agents/v4-flash-worker.toml").read_text() == (
        'name = "v4_flash_worker"\nmodel = "stale"\n'
    )
    assert (home / "AGENTS.md").read_text() == "original agents\n"
    assert not (home / "hooks.json").exists()
    assert not (home / "config.toml").exists()
    assert not (home / "skills").exists()
    assert not mod.state_dir(home).exists()
