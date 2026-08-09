"""RED tests for the installer lifecycle review/verify findings.

Each test pins one required fix:
- remove_hook_group must never delete a pre-existing hooks.json with unrelated
  content merely because the post-install whole-file hash matches state.
- Credentials/base URLs must be TOML-escaped; validate must gate the exit code
  inside the rollback-protected transaction.
- --add must be atomic and strict (conflict -> exit 2, nothing written/owned).
- sync_embedded_payload.py --check must exist and be read-only.
- restore must honor --yes for absent-snapshot entries and report the
  pre-restore safety backup ID.
- status must compare the Hook to the installed state hash, not to the current
  interpreter's build.
- A noninteractive update must preserve an existing env_key credential.
- --json usage errors must emit a JSON object on stdout.
- TTY-like credential prompting under --json must keep stdout a single JSON doc.
- --dry-run --json install results must report planned changes, not applied ones.
- Pre-change backup failures must be clean exit-1 errors with zero writes.
- A state-save failure must roll back the transaction and exit 1.
- Malformed hooks.json container shapes must fail cleanly in remove/status.
"""

import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tomllib

import pytest

import codex_deepseek_subagent_setup as mod
from conftest import make_args, make_home, setup_install

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SYNC_SCRIPT = REPO_ROOT / "scripts" / "sync_embedded_payload.py"


# ---------------------------------------------------------------------------
# remove_hook_group: pre-existing unrelated content must survive removal
# ---------------------------------------------------------------------------


def _seed_hooks(home, document):
    target = home / "hooks.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return target


def test_remove_preserves_preinstalled_hooks_json(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    _seed_hooks(
        home,
        {
            "description": "user hooks",
            "hooks": {
                "SubagentStart": [
                    {
                        "matcher": "^other$",
                        "hooks": [{"type": "command", "command": "keep"}],
                    }
                ]
            },
        },
    )
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    assert mod.cmd_remove(make_args(backup_dir=str(backup_root), yes=True)) == 0
    assert (home / "hooks.json").exists()
    doc = json.loads((home / "hooks.json").read_text())
    assert doc["description"] == "user hooks"
    matchers = [g.get("matcher") for g in doc["hooks"]["SubagentStart"]]
    assert "^v4_flash_worker$" not in matchers
    assert "^other$" in matchers


def test_remove_preserves_preinstalled_hooks_other_category(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    _seed_hooks(
        home,
        {"hooks": {"PreToolUse": [{"matcher": "^Bash$", "hooks": []}]}},
    )
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    assert mod.cmd_remove(make_args(backup_dir=str(backup_root), yes=True)) == 0
    doc = json.loads((home / "hooks.json").read_text())
    assert "PreToolUse" in doc["hooks"]
    assert not any(
        g.get("matcher") == "^v4_flash_worker$"
        for g in doc["hooks"].get("SubagentStart", [])
    )


def test_remove_deletes_installer_created_hooks_json(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    assert mod.cmd_remove(make_args(backup_dir=str(backup_root), yes=True)) == 0
    assert not (home / "hooks.json").exists()


# ---------------------------------------------------------------------------
# TOML escaping of credentials and base URLs
# ---------------------------------------------------------------------------


def test_toml_string_escapes_special_characters():
    value = 'sk-a"b\\c\t'
    literal = mod.toml_string(value)
    assert literal.startswith('"') and literal.endswith('"')
    parsed = tomllib.loads(f"key = {literal}")
    assert parsed["key"] == value


def test_agent_toml_escapes_base_url_and_credentials():
    base_url = 'https://api.example/v1/query?key="quoted"&path=C:\\tools'
    token = 'sk-a"b\\c'
    content = mod.agent_toml_content(
        base_url, f"experimental_bearer_token = {mod.toml_string(token)}"
    )
    data = tomllib.loads(content)
    ds = data["model_providers"]["deepseek"]
    assert ds["base_url"] == base_url
    assert ds["experimental_bearer_token"] == token


def test_resolve_credentials_escapes_user_input(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(mod, "load_opencode_go_credentials", lambda: (None, None))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    it = iter(['https://api.example/v1?key="q"', 'sk-a"b\\c'])
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(it))
    base, lines, source = mod.resolve_credentials(home)
    assert source == "user input"
    content = mod.agent_toml_content(base, lines)
    data = tomllib.loads(content)
    assert data["model_providers"]["deepseek"]["base_url"] == 'https://api.example/v1?key="q"'
    assert data["model_providers"]["deepseek"]["experimental_bearer_token"] == 'sk-a"b\\c'


# ---------------------------------------------------------------------------
# validate() returns success/failure and gates the transaction exit code
# ---------------------------------------------------------------------------


def test_validate_returns_true_for_valid_home(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    assert mod.validate(home) is True


def test_validate_returns_false_for_broken_config(tmp_path, capsys):
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("[broken\n", encoding="utf-8")
    assert mod.validate(home) is False


def test_install_rolls_back_and_exits_1_on_validation_failure(
    tmp_path, monkeypatch, capsys
):
    home = setup_install(monkeypatch, tmp_path)
    (home / "AGENTS.md").write_text("pre-existing agents\n", encoding="utf-8")
    before = (home / "AGENTS.md").read_bytes()
    monkeypatch.setattr(mod, "validate", lambda codex_home: False)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 1
    assert (home / "AGENTS.md").read_bytes() == before
    assert not (home / "skills").exists()
    assert not mod.state_dir(home).exists()


# ---------------------------------------------------------------------------
# --add is atomic and strict
# ---------------------------------------------------------------------------


def test_add_conflict_exits_2_and_writes_nothing(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    agent = home / "agents/v4-flash-worker.toml"
    agent.parent.mkdir(parents=True)
    agent.write_text('name = "v4_flash_worker"\nmodel = "custom"\n', encoding="utf-8")
    backup_root = tmp_path / "backups"
    assert mod.cmd_add(make_args(backup_dir=str(backup_root))) == 2
    assert agent.read_text() == 'name = "v4_flash_worker"\nmodel = "custom"\n'
    assert not (home / "skills").exists()
    assert not (home / "hooks.json").exists()
    assert not (home / "config.toml").exists()
    assert not mod.state_dir(home).exists()
    assert len(mod.list_backups(backup_root)) == 0
    out = capsys.readouterr().out
    assert "conflict" in out.lower()


def test_add_agents_md_without_block_is_conflict(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    (home / "AGENTS.md").write_text("# user rules\nkeep\n", encoding="utf-8")
    backup_root = tmp_path / "backups"
    assert mod.cmd_add(make_args(backup_dir=str(backup_root))) == 2
    assert (home / "AGENTS.md").read_text() == "# user rules\nkeep\n"
    assert not mod.state_dir(home).exists()


def test_add_hooks_json_without_group_is_conflict(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    _seed_hooks(
        home,
        {"description": "user hooks", "hooks": {"SubagentStart": []}},
    )
    before = (home / "hooks.json").read_bytes()
    backup_root = tmp_path / "backups"
    assert mod.cmd_add(make_args(backup_dir=str(backup_root))) == 2
    assert (home / "hooks.json").read_bytes() == before
    assert not mod.state_dir(home).exists()


def test_add_identical_partial_files_are_not_conflicts(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    config = home / "config.toml"
    config.write_text(
        "[shell_environment_policy.set]\n"
        'PYTHONUTF8 = "1"\n'
        'PYTHONIOENCODING = "utf-8"\n',
        encoding="utf-8",
    )
    backup_root = tmp_path / "backups"
    assert mod.cmd_add(make_args(backup_dir=str(backup_root))) == 0
    assert (home / "agents/v4-flash-worker.toml").exists()


# ---------------------------------------------------------------------------
# sync_embedded_payload.py --check
# ---------------------------------------------------------------------------


def load_sync_module():
    spec = importlib.util.spec_from_file_location("sync_embedded_payload", SYNC_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sync_check_exits_zero_on_committed_tree():
    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_sync_check_detects_payload_drift(tmp_path, monkeypatch):
    sync = load_sync_module()
    tampered = tmp_path / "payload"
    for rel in sync.PAYLOAD_FILES:
        destination = tampered / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((sync.PAYLOAD_DIR / rel).read_bytes())
    drifted = (tampered / "SKILL.md").read_bytes() + b"# drift\n"
    (tampered / "SKILL.md").write_bytes(drifted)
    monkeypatch.setattr(sync, "PAYLOAD_DIR", tampered)
    assert sync.check_drift()


def test_sync_check_detects_version_drift(tmp_path, monkeypatch):
    sync = load_sync_module()
    monkeypatch.setattr(sync, "read_version", lambda: "9.9.9")
    assert sync.check_drift()


# ---------------------------------------------------------------------------
# restore: --yes deletes drifted absent-snapshot extras; safety backup reported
# ---------------------------------------------------------------------------


def test_restore_yes_deletes_drifted_installed_extra(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_backup(make_args(backup_dir=str(backup_root))) == 0
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    skill = home / "skills/use-v4-flash-worker/SKILL.md"
    skill.write_text("user edit", encoding="utf-8")
    assert (
        mod.cmd_restore(make_args(backup_dir=str(backup_root), restore="latest", yes=True))
        == 0
    )
    assert not skill.exists()


def test_restore_without_yes_refuses_drifted_extra(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_backup(make_args(backup_dir=str(backup_root))) == 0
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    skill = home / "skills/use-v4-flash-worker/SKILL.md"
    skill.write_text("user edit", encoding="utf-8")
    assert mod.cmd_restore(make_args(backup_dir=str(backup_root), restore="latest")) == 2
    assert skill.exists()


def test_restore_reports_safety_backup_id(tmp_path, monkeypatch, capsys, json_mode):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    assert (
        mod.cmd_restore(
            make_args(backup_dir=str(backup_root), restore="latest", yes=True, json=True)
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["safety_backup_id"]
    assert data["safety_backup_id"] != data["backup_id"]
    assert (backup_root / data["safety_backup_id"]).is_dir()


# ---------------------------------------------------------------------------
# status: compare against the installed state hash, not the interpreter
# ---------------------------------------------------------------------------


def test_status_no_false_alert_with_different_python(tmp_path, monkeypatch, capsys, json_mode):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    args = make_args(
        backup_dir=str(backup_root),
        python_executable=r"C:\Python 3.14\python.exe",
    )
    assert mod.cmd_install(args) == 0
    assert (
        mod.cmd_status(
            make_args(
                backup_dir=str(backup_root),
                python_executable=r"D:\other\python.exe",
                json=True,
            )
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["hook_definition_changed"] is False
    assert data["hook_review_required"] is False


def test_status_detects_real_hook_change(tmp_path, monkeypatch, capsys, json_mode):
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    hooks = json.loads((home / "hooks.json").read_text())
    hooks["hooks"]["SubagentStart"][0]["hooks"][0]["timeout"] = 99
    (home / "hooks.json").write_text(json.dumps(hooks, indent=2), encoding="utf-8")
    assert mod.cmd_status(make_args(backup_dir=str(backup_root), json=True)) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["hook_definition_changed"] is True


# ---------------------------------------------------------------------------
# env_key credential preservation on noninteractive update
# ---------------------------------------------------------------------------


def test_existing_agent_credentials_env_key(tmp_path):
    home = tmp_path / "home"
    agent = home / "agents" / "v4-flash-worker.toml"
    agent.parent.mkdir(parents=True)
    agent.write_text(
        'name = "v4_flash_worker"\n'
        "[model_providers.deepseek]\n"
        'base_url = "https://gateway.example"\n'
        'env_key = "MY_CUSTOM_KEY"\n',
        encoding="utf-8",
    )
    existing = mod._existing_agent_credentials(home)
    assert existing is not None
    base, lines = existing
    assert base == "https://gateway.example"
    assert "env_key" in lines
    assert "MY_CUSTOM_KEY" in lines


def test_update_preserves_env_key_credential(tmp_path, monkeypatch, capsys):
    home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(mod, "is_windows", lambda: False)
    monkeypatch.setattr(
        mod, "load_opencode_go_credentials", lambda: ("https://kimi.example", "sk-kimi")
    )
    agent = home / "agents" / "v4-flash-worker.toml"
    agent.parent.mkdir(parents=True)
    agent.write_text(
        'name = "v4_flash_worker"\n'
        "[model_providers.deepseek]\n"
        'base_url = "https://gateway.example"\n'
        'env_key = "MY_CUSTOM_KEY"\n',
        encoding="utf-8",
    )
    backup_root = tmp_path / "backups"
    assert mod.cmd_update(make_args(backup_dir=str(backup_root))) == 0
    data = tomllib.loads(agent.read_text())
    ds = data["model_providers"]["deepseek"]
    assert ds["env_key"] == "MY_CUSTOM_KEY"
    assert "experimental_bearer_token" not in ds
    assert ds["base_url"] == "https://gateway.example"


# ---------------------------------------------------------------------------
# JSON usage-error coverage
# ---------------------------------------------------------------------------


def test_conflicting_actions_json(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["prog", "--add", "--remove", "--json"])
    previous = mod._OUTPUT_JSON
    try:
        assert mod.main() == 2
    finally:
        mod._OUTPUT_JSON = previous
    data = json.loads(capsys.readouterr().out)
    assert data["exit_code"] == 2

# ---------------------------------------------------------------------------
# JSON machine interface: TTY-like stdin, dry-run semantics, clean failures
# ---------------------------------------------------------------------------


def _assert_single_json_document(text):
    """Assert text is exactly one JSON document followed by only whitespace."""
    document, end = json.JSONDecoder().raw_decode(text)
    assert text[end:].strip() == ""
    return document


def test_install_json_stdout_single_document_with_tty_stdin(
    tmp_path, monkeypatch, capsys, json_mode
):
    """TTY-like credential prompting must not pollute --json stdout."""
    home = make_home(tmp_path)
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(mod, "load_opencode_go_credentials", lambda: (None, None))
    monkeypatch.setattr(mod, "is_windows", lambda: False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    it = iter(["https://api.example/v1", "sk-tty-json"])
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(it))
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root), json=True)) == 0
    captured = capsys.readouterr()
    document = _assert_single_json_document(captured.out)
    assert document["exit_code"] == 0
    assert document["credential_source"] == "user input"
    assert "base URL" not in captured.out
    assert "API key" not in captured.out
    assert "base URL" in captured.err
    assert "API key" in captured.err


def test_add_conflict_json_single_document_with_tty_stdin(
    tmp_path, monkeypatch, capsys, json_mode
):
    """Clean --json failures with TTY-like stdin still emit one JSON document."""
    home = make_home(tmp_path)
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(mod, "load_opencode_go_credentials", lambda: (None, None))
    agent = home / "agents/v4-flash-worker.toml"
    agent.parent.mkdir(parents=True)
    agent.write_text('name = "v4_flash_worker"\nmodel = "custom"\n', encoding="utf-8")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    it = iter(["https://api.example/v1", "sk-tty-json"])
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(it))
    backup_root = tmp_path / "backups"
    assert mod.cmd_add(make_args(backup_dir=str(backup_root), json=True)) == 2
    captured = capsys.readouterr()
    document = _assert_single_json_document(captured.out)
    assert document["exit_code"] == 2
    assert document["conflicts"] == ["agents/v4-flash-worker.toml"]
    assert "base URL" not in captured.out
    assert "base URL" in captured.err


def test_install_json_dry_run_reports_planned_not_applied(
    tmp_path, monkeypatch, capsys, json_mode
):
    """--dry-run --json must never let planned changes read as applied writes."""
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    args = make_args(backup_dir=str(backup_root), dry_run=True, json=True)
    assert mod.cmd_install(args) == 0
    captured = capsys.readouterr()
    document = _assert_single_json_document(captured.out)
    assert document["dry_run"] is True
    assert document["changed"] == 0
    assert document["files_changed"] == []
    assert document["planned_changes"] == len(mod.MANAGED_FILES)
    assert set(document["planned_files"]) == set(mod.MANAGED_FILES)
    assert document["backup_id"] is None
    assert not (home / "agents/v4-flash-worker.toml").exists()
    assert not mod.state_dir(home).exists()
    assert len(mod.list_backups(backup_root)) == 0


def test_install_json_success_keeps_applied_semantics(
    tmp_path, monkeypatch, capsys, json_mode
):
    """A real (non-dry-run) install keeps changed/files_changed as applied."""
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root), json=True)) == 0
    document = _assert_single_json_document(capsys.readouterr().out)
    assert document["changed"] == len(mod.MANAGED_FILES)
    assert set(document["files_changed"]) == set(mod.MANAGED_FILES)


def test_install_backup_failure_emits_clean_json_no_writes(
    tmp_path, monkeypatch, capsys, json_mode
):
    """A pre-change backup failure is a clean exit-1 JSON error, zero writes."""
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"

    def boom_backup(codex_home, backup_root, action="install"):
        raise PermissionError("backup dir denied")

    monkeypatch.setattr(mod, "create_backup", boom_backup)
    assert mod.cmd_install(make_args(backup_dir=str(backup_root), json=True)) == 1
    captured = capsys.readouterr()
    document = _assert_single_json_document(captured.out)
    assert document["exit_code"] == 1
    assert document["changed"] == 0
    assert document["files_changed"] == []
    assert document["backup_id"] is None
    assert "backup" in document["error"].lower()
    assert not (home / "agents/v4-flash-worker.toml").exists()
    assert not (home / "skills").exists()
    assert not mod.state_dir(home).exists()
    assert len(mod.list_backups(backup_root)) == 0


def test_install_backup_failure_human_exits_1_no_writes(tmp_path, monkeypatch, capsys):
    """The same backup failure in human mode is a clean exit-1 error."""
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"

    def boom_backup(codex_home, backup_root, action="install"):
        raise PermissionError("backup dir denied")

    monkeypatch.setattr(mod, "create_backup", boom_backup)
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 1
    out = capsys.readouterr().out
    assert "backup failed" in out.lower()
    assert not (home / "agents/v4-flash-worker.toml").exists()
    assert not mod.state_dir(home).exists()


def test_create_backup_removes_partial_directory_on_failure(tmp_path, monkeypatch):
    """create_backup must not leave a half-written snapshot dir when it fails."""
    home = make_home(tmp_path)
    agent = home / "agents/v4-flash-worker.toml"
    agent.parent.mkdir(parents=True)
    agent.write_text('name = "v4_flash_worker"\n', encoding="utf-8")

    def flaky_copy(src, dst, *args, **kwargs):
        raise PermissionError("copy denied")

    monkeypatch.setattr(mod.shutil, "copy2", flaky_copy)
    backup_root = tmp_path / "backups"
    with pytest.raises(PermissionError):
        mod.create_backup(home, backup_root, action="install")
    assert not backup_root.exists() or not any(backup_root.iterdir())


def test_install_rolls_back_and_exits_1_on_state_save_failure(
    tmp_path, monkeypatch, capsys
):
    """A state-save failure rolls back the transaction and exits 1 cleanly."""
    home = setup_install(monkeypatch, tmp_path)
    (home / "AGENTS.md").write_text("pre-existing agents\n", encoding="utf-8")
    before = (home / "AGENTS.md").read_bytes()

    def boom_state(codex_home, state):
        raise PermissionError("state save denied")

    monkeypatch.setattr(mod, "save_state", boom_state)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 1
    assert (home / "AGENTS.md").read_bytes() == before
    assert not (home / "skills").exists()
    assert not mod.state_dir(home).exists()
    out = capsys.readouterr().out
    assert "restoring the pre-change snapshot" in out


# ---------------------------------------------------------------------------
# Malformed hooks.json container shapes fail cleanly in remove/status
# ---------------------------------------------------------------------------


def test_remove_malformed_hooks_json_clean_failure_no_writes(
    tmp_path, monkeypatch, capsys, json_mode
):
    """--remove with a malformed hooks.json aborts cleanly with zero writes."""
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    hooks_target = home / "hooks.json"
    before_agent = (home / "agents/v4-flash-worker.toml").read_bytes()
    hooks_target.write_text(json.dumps({"hooks": []}), encoding="utf-8")
    malformed_hooks = hooks_target.read_bytes()
    assert (
        mod.cmd_remove(make_args(backup_dir=str(backup_root), yes=True, json=True))
        == 1
    )
    captured = capsys.readouterr()
    document = _assert_single_json_document(captured.out)
    assert document["exit_code"] == 1
    assert document["removed_files"] == []
    assert document["backup_id"] is None
    assert (home / "agents/v4-flash-worker.toml").read_bytes() == before_agent
    assert hooks_target.read_bytes() == malformed_hooks
    assert mod.state_dir(home).exists()


def test_remove_malformed_hooks_json_human_clean_failure(tmp_path, monkeypatch, capsys):
    """Human-mode --remove reports the malformed hooks.json and writes nothing."""
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    hooks_target = home / "hooks.json"
    hooks_target.write_text(
        json.dumps({"hooks": {"SubagentStart": "not-a-list"}}), encoding="utf-8"
    )
    assert mod.cmd_remove(make_args(backup_dir=str(backup_root), yes=True)) == 1
    out = capsys.readouterr().out
    assert "hooks.json" in out
    assert "malformed" in out.lower()
    assert (home / "agents/v4-flash-worker.toml").exists()


def test_status_malformed_hooks_json_reports_hooks_error(
    tmp_path, monkeypatch, capsys, json_mode
):
    """--status --json reports a malformed hooks.json, never a traceback."""
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    (home / "hooks.json").write_text(json.dumps({"hooks": []}), encoding="utf-8")
    assert mod.cmd_status(make_args(backup_dir=str(backup_root), json=True)) == 0
    captured = capsys.readouterr()
    document = _assert_single_json_document(captured.out)
    assert document["hooks_error"]
    assert "hooks" in document["hooks_error"].lower()


def test_status_malformed_hooks_json_human_fail_line(tmp_path, monkeypatch, capsys):
    """Human-mode --status flags a malformed hooks.json explicitly."""
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    (home / "hooks.json").write_text('{"hooks": []}', encoding="utf-8")
    assert mod.cmd_status(make_args(backup_dir=str(backup_root))) == 0
    out = capsys.readouterr().out
    assert "malformed" in out.lower()



# ---------------------------------------------------------------------------
# Standalone --backup failures are clean exit-1 JSON/human errors
# ---------------------------------------------------------------------------


def test_backup_json_failure_emits_clean_json_no_partial_dir(
    tmp_path, monkeypatch, capsys, json_mode
):
    """A standalone --backup --json failure is one clean JSON doc, exit 1."""
    home = make_home(tmp_path)
    backup_root = tmp_path / "backups"

    def boom_backup(codex_home, backup_root, action="backup"):
        raise PermissionError("backup dir denied")

    monkeypatch.setattr(mod, "create_backup", boom_backup)
    assert mod.cmd_backup(make_args(backup_dir=str(backup_root), json=True)) == 1
    captured = capsys.readouterr()
    document = _assert_single_json_document(captured.out)
    assert document["exit_code"] == 1
    assert document["action"] == "backup"
    assert document["backup_id"] is None
    assert "backup" in document["error"].lower()
    assert not backup_root.exists() or not any(backup_root.iterdir())


def test_backup_human_failure_exits_1_no_traceback(tmp_path, monkeypatch, capsys):
    """A standalone --backup failure in human mode is a clean exit-1 error."""
    home = make_home(tmp_path)
    backup_root = tmp_path / "backups"

    def boom_backup(codex_home, backup_root, action="backup"):
        raise PermissionError("backup dir denied")

    monkeypatch.setattr(mod, "create_backup", boom_backup)
    assert mod.cmd_backup(make_args(backup_dir=str(backup_root))) == 1
    out = capsys.readouterr().out
    assert "backup failed" in out.lower()
    assert not backup_root.exists() or not any(backup_root.iterdir())


# ---------------------------------------------------------------------------
# --status --json always includes exit_code
# ---------------------------------------------------------------------------


def test_status_json_includes_exit_code(tmp_path, monkeypatch, capsys, json_mode):
    """Every --status --json document carries exit_code for a uniform schema."""
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_status(make_args(backup_dir=str(backup_root), json=True)) == 0
    document = _assert_single_json_document(capsys.readouterr().out)
    assert document["exit_code"] == 0
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    assert mod.cmd_status(make_args(backup_dir=str(backup_root), json=True)) == 0
    document = _assert_single_json_document(capsys.readouterr().out)
    assert document["exit_code"] == 0


# ---------------------------------------------------------------------------
# hooks: null is rejected as a non-object by install/status/remove
# ---------------------------------------------------------------------------


def test_install_rejects_hooks_null_clean_json(tmp_path, monkeypatch, capsys, json_mode):
    """Install with hooks: null fails planning cleanly with zero writes."""
    home = setup_install(monkeypatch, tmp_path)
    _seed_hooks(home, {"description": "user hooks", "hooks": None})
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root), json=True)) == 1
    captured = capsys.readouterr()
    document = _assert_single_json_document(captured.out)
    assert document["exit_code"] == 1
    assert document["changed"] == 0
    assert "planning failed" in captured.err.lower()
    assert "hooks" in captured.err.lower()
    assert not (home / "agents/v4-flash-worker.toml").exists()
    assert not mod.state_dir(home).exists()
    assert len(mod.list_backups(backup_root)) == 0


def test_status_reports_hooks_null_as_hooks_error(tmp_path, monkeypatch, capsys, json_mode):
    """--status --json reports hooks: null as a structural hooks error."""
    home = setup_install(monkeypatch, tmp_path)
    _seed_hooks(home, {"description": "user hooks", "hooks": None})
    backup_root = tmp_path / "backups"
    assert mod.cmd_status(make_args(backup_dir=str(backup_root), json=True)) == 0
    document = _assert_single_json_document(capsys.readouterr().out)
    assert document["hooks_error"]
    assert "hooks" in document["hooks_error"].lower()


def test_remove_rejects_hooks_null_no_writes(tmp_path, monkeypatch, capsys, json_mode):
    """--remove with hooks: null aborts cleanly with zero writes and no backup."""
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    hooks_target = home / "hooks.json"
    hooks_target.write_text(
        json.dumps({"description": "user hooks", "hooks": None}), encoding="utf-8"
    )
    before_agent = (home / "agents/v4-flash-worker.toml").read_bytes()
    malformed_hooks = hooks_target.read_bytes()
    backups_before = len(mod.list_backups(backup_root))
    assert (
        mod.cmd_remove(make_args(backup_dir=str(backup_root), yes=True, json=True))
        == 1
    )
    captured = capsys.readouterr()
    document = _assert_single_json_document(captured.out)
    assert document["exit_code"] == 1
    assert document["removed_files"] == []
    assert document["backup_id"] is None
    assert (home / "agents/v4-flash-worker.toml").read_bytes() == before_agent
    assert hooks_target.read_bytes() == malformed_hooks
    assert mod.state_dir(home).exists()
    assert len(mod.list_backups(backup_root)) == backups_before
