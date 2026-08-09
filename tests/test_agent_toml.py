"""Agent TOML generation: content, idempotence, permissions."""

import os
import tomllib

import codex_deepseek_subagent_setup as mod

BASE = "https://api.deepseek.com"
BEARER = 'experimental_bearer_token = "sk-test"'


def test_writes_full_agent_file(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "is_windows", lambda: False)
    assert mod.ensure_agent_toml(tmp_path, BASE, BEARER, dry_run=False)
    data = tomllib.loads(
        (tmp_path / "agents" / "v4-flash-worker.toml").read_text()
    )
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


def test_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "is_windows", lambda: False)
    mod.ensure_agent_toml(tmp_path, BASE, BEARER, dry_run=False)
    assert not mod.ensure_agent_toml(tmp_path, BASE, BEARER, dry_run=False)


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "is_windows", lambda: False)
    assert mod.ensure_agent_toml(tmp_path, BASE, BEARER, dry_run=True)
    assert not (tmp_path / "agents" / "v4-flash-worker.toml").exists()


def test_mode_0600_on_posix(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "is_windows", lambda: False)
    mod.ensure_agent_toml(tmp_path, BASE, BEARER, dry_run=False)
    if os.name != "nt":
        mode = (tmp_path / "agents" / "v4-flash-worker.toml").stat().st_mode
        assert mode & 0o777 == 0o600
