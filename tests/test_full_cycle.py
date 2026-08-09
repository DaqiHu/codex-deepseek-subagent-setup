"""End-to-end install -> backup -> poison -> restore -> idempotence."""

import argparse
import tomllib

import codex_deepseek_subagent_setup as mod

CRED = ("https://kimi.example", 'experimental_bearer_token = "sk-test"', "test")


def make_args(**overrides):
    base = dict(
        dry_run=False,
        backup_dir=None,
        skip_backup=False,
        restore=None,
        manual=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_full_cycle(tmp_path, monkeypatch, capsys):
    home = tmp_path / "codex-home"
    backup_root = tmp_path / "backups"
    (home / "agents").mkdir(parents=True)
    (home / "agents" / "v4-flash-worker.toml").write_text(
        'name = "v4_flash_worker"\nmodel = "stale"\n'
    )
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(mod, "resolve_credentials", lambda: CRED)
    monkeypatch.setattr(mod, "is_windows", lambda: False)

    # run 1: install + backup
    args = make_args(backup_dir=str(backup_root))
    assert mod.cmd_install(args) == 0
    backups = mod.list_backups(backup_root)
    assert len(backups) == 1

    # run 2: idempotent, no new backup
    assert mod.cmd_install(args) == 0
    out = capsys.readouterr().out
    assert "0 file(s) changed" in out
    assert len(mod.list_backups(backup_root)) == 1

    # poison + restore
    (home / "agents" / "v4-flash-worker.toml").write_text("garbage")
    assert mod.cmd_restore(make_args(backup_dir=str(backup_root), restore="latest")) == 0
    data = tomllib.loads((home / "agents" / "v4-flash-worker.toml").read_text())
    assert data["sandbox_mode"] == "danger-full-access"
    assert data["model"] == "deepseek-v4-flash"
