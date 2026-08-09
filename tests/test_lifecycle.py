"""Lifecycle commands: install/add/update/backup/list/status/remove/dry-run."""

import json
import sys
import tomllib

import codex_deepseek_subagent_setup as mod
from conftest import make_args, setup_install


def test_default_install_creates_everything(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    for rel in mod.MANAGED_FILES:
        assert (home / rel).exists(), rel
    state = mod.load_state(home)
    assert state["payload_version"] == mod.PAYLOAD_VERSION
    for rel in mod.MANAGED_FILES:
        assert state["files"][rel] == mod.sha256_of(home / rel)
    for payload_rel, dest_rel in mod.PAYLOAD_DESTINATIONS.items():
        assert (home / dest_rel).read_bytes() == mod.payload_bytes(payload_rel)
    hook_script = home / "hooks/codex-deepseek-subagent/plaintext_handoff.py"
    assert hook_script.read_bytes() == mod.payload_bytes("scripts/plaintext_handoff.py")
    assert len(mod.list_backups(backup_root)) == 1
    # hook review required on first install
    out = capsys.readouterr().out
    assert "hook definition changed" in out


def test_install_json_result(tmp_path, monkeypatch, capsys, json_mode):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    args = make_args(backup_dir=str(backup_root), json=True)
    assert mod.cmd_install(args) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["action"] == "install"
    assert data["changed"] == len(mod.MANAGED_FILES)
    assert data["hook_review_required"] is True
    assert data["agents_block_updated"] is True
    assert data["backup_id"]


def test_idempotent_second_run_no_backup(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    args = make_args(backup_dir=str(backup_root))
    assert mod.cmd_install(args) == 0
    assert mod.cmd_install(args) == 0
    out = capsys.readouterr().out
    assert "0 file(s) changed" in out
    assert len(mod.list_backups(backup_root)) == 1


def test_add_creates_missing_only(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_add(make_args(backup_dir=str(backup_root))) == 0
    for rel in mod.MANAGED_FILES:
        assert (home / rel).exists(), rel
    assert mod.cmd_add(make_args(backup_dir=str(backup_root))) == 0
    out = capsys.readouterr().out
    assert "0 file(s) changed" in out


def test_add_never_overwrites_existing(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    agent = home / "agents/v4-flash-worker.toml"
    agent.parent.mkdir(parents=True, exist_ok=True)
    agent.write_text('name = "v4_flash_worker"\nmodel = "custom"\n', encoding="utf-8")
    # --add is atomic and strict: a conflicting existing artifact is a refusal
    # (exit 2) and nothing else is written or owned.
    assert mod.cmd_add(make_args(backup_dir=str(backup_root))) == 2
    assert agent.read_text() == 'name = "v4_flash_worker"\nmodel = "custom"\n'
    assert not (home / "skills").exists()
    assert not mod.state_dir(home).exists()
    out = capsys.readouterr().out
    assert "use --update" in out


def test_update_refreshes_stale_managed_file(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    skill = home / "skills/use-v4-flash-worker/SKILL.md"
    skill.write_text("stale", encoding="utf-8")
    assert mod.cmd_update(make_args(backup_dir=str(backup_root))) == 0
    assert skill.read_bytes() == mod.payload_bytes("SKILL.md")


def test_backup_and_list_backups(tmp_path, monkeypatch, capsys, json_mode):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_backup(make_args(backup_dir=str(backup_root))) == 0
    assert (
        mod.cmd_list_backups(make_args(backup_dir=str(backup_root), json=True)) == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["action"] == "list-backups"
    assert len(data["backups"]) == 1
    assert data["backups"][0]["id"]


def test_status_json_shape(tmp_path, monkeypatch, capsys, json_mode):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    assert mod.cmd_status(make_args(backup_dir=str(backup_root), json=True)) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["action"] == "status"
    assert data["installed"] is True
    assert data["files"]["agents/v4-flash-worker.toml"]["owned"] is True
    assert data["files"]["AGENTS.md"]["owned"] is True
    assert data["hook_definition_changed"] is False
    assert len(data["backups"]) == 1


def test_status_shows_missing_after_remove(tmp_path, monkeypatch, capsys, json_mode):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    assert mod.cmd_remove(make_args(backup_dir=str(backup_root), yes=True)) == 0
    assert mod.cmd_status(make_args(backup_dir=str(backup_root), json=True)) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["installed"] is False
    assert data["files"]["agents/v4-flash-worker.toml"]["present"] is False


def test_conflicting_actions_rejected(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", ["prog", "--add", "--remove"])
    assert mod.main() == 2


def test_dry_run_writes_nothing_for_every_action(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    before = {
        rel: (home / rel).read_bytes() if (home / rel).exists() else None
        for rel in mod.MANAGED_FILES
    }
    backups_before = [b.name for b in mod.list_backups(backup_root)]
    for runner in (
        mod.cmd_install,
        mod.cmd_add,
        mod.cmd_update,
        mod.cmd_backup,
        mod.cmd_status,
        mod.cmd_restore,
        mod.cmd_remove,
    ):
        assert (
            runner(
                make_args(
                    backup_dir=str(backup_root),
                    dry_run=True,
                    restore="latest",
                    yes=True,
                )
            )
            == 0
        )
    after = {
        rel: (home / rel).read_bytes() if (home / rel).exists() else None
        for rel in mod.MANAGED_FILES
    }
    assert after == before
    assert [b.name for b in mod.list_backups(backup_root)] == backups_before


def test_rollback_on_failed_write(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    (home / "AGENTS.md").write_text("pre-existing agents\n", encoding="utf-8")
    (home / "config.toml").write_text('model = "x"\n', encoding="utf-8")
    before = {
        rel: (home / rel).read_bytes() for rel in ("AGENTS.md", "config.toml")
    }
    real_write = mod.write_bytes_atomically
    calls = {"n": 0}

    def flaky(path, data):
        calls["n"] += 1
        if calls["n"] >= 4:
            raise OSError("simulated write failure")
        return real_write(path, data)

    monkeypatch.setattr(mod, "write_bytes_atomically", flaky)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 1
    assert (home / "AGENTS.md").read_bytes() == before["AGENTS.md"]
    assert (home / "config.toml").read_bytes() == before["config.toml"]
    assert not (home / "skills").exists()
    assert not mod.state_dir(home).exists()
