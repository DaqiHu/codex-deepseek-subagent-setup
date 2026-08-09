"""Agent TOML generation: content, permissions, credential preservation."""

import os
import stat
import tomllib

import codex_deepseek_subagent_setup as mod
from conftest import make_args, setup_install

BASE = "https://api.deepseek.com"
BEARER = 'experimental_bearer_token = "sk-test"'


def test_writes_full_agent_file(tmp_path):
    home = tmp_path / "codex-home"
    content = mod.agent_toml_content(BASE, BEARER)
    target = home / "agents" / "v4-flash-worker.toml"
    target.parent.mkdir(parents=True)
    target.write_text(content, encoding="utf-8")
    data = tomllib.loads(target.read_text())
    assert data["name"] == "v4_flash_worker"
    assert data["model"] == "deepseek-v4-flash"
    assert data["model_provider"] == "deepseek"
    assert data["model_context_window"] == 1000000
    assert data["sandbox_mode"] == "danger-full-access"
    ds = data["model_providers"]["deepseek"]
    assert ds["base_url"] == BASE
    assert ds["wire_api"] == "responses"
    assert ds["experimental_bearer_token"] == "sk-test"
    assert "env_key" not in ds


def test_posix_chmod_0600(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path, windows=False)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    if os.name != "nt":
        mode = stat.S_IMODE((home / "agents/v4-flash-worker.toml").stat().st_mode)
        assert mode == 0o600


def test_windows_no_chmod(tmp_path, monkeypatch, capsys):
    home = setup_install(monkeypatch, tmp_path, windows=True)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    if os.name != "nt":
        mode = stat.S_IMODE((home / "agents/v4-flash-worker.toml").stat().st_mode)
        assert mode != 0o600


def test_update_preserves_existing_token(tmp_path, monkeypatch, capsys):
    home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(mod, "is_windows", lambda: False)
    agent = home / "agents" / "v4-flash-worker.toml"
    agent.parent.mkdir(parents=True)
    agent.write_text(
        'name = "v4_flash_worker"\n'
        "[model_providers.deepseek]\n"
        'base_url = "https://preserved.example"\n'
        'experimental_bearer_token = "sk-existing"\n',
        encoding="utf-8",
    )
    backup_root = tmp_path / "backups"
    assert mod.cmd_update(make_args(backup_dir=str(backup_root))) == 0
    data = tomllib.loads(agent.read_text())
    assert data["model_providers"]["deepseek"]["experimental_bearer_token"] == "sk-existing"
    assert data["model_providers"]["deepseek"]["base_url"] == "https://preserved.example"


def test_explicit_creds_overwrite(tmp_path, monkeypatch, capsys):
    home = setup_install(
        monkeypatch,
        tmp_path,
        cred=("https://new.example", 'experimental_bearer_token = "sk-new"', "user input"),
    )
    backup_root = tmp_path / "backups"
    assert mod.cmd_update(make_args(backup_dir=str(backup_root))) == 0
    data = tomllib.loads((home / "agents/v4-flash-worker.toml").read_text())
    assert data["model_providers"]["deepseek"]["experimental_bearer_token"] == "sk-new"
    assert data["model_providers"]["deepseek"]["base_url"] == "https://new.example"
