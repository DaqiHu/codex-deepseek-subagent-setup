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
"""

import importlib.util
import json
import pathlib
import subprocess
import sys
import tomllib

import codex_deepseek_subagent_setup as mod
from conftest import make_args, setup_install

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
