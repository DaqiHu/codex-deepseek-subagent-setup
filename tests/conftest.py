"""Shared fixtures and helpers for the installer lifecycle tests."""

import argparse
import pytest


@pytest.fixture
def json_mode():
    """Route human output to stderr and leave stdout JSON-only (like --json)."""
    mod._OUTPUT_JSON = True
    yield
    mod._OUTPUT_JSON = False


import codex_deepseek_subagent_setup as mod


def make_args(**overrides):
    base = dict(
        dry_run=False,
        backup_dir=None,
        skip_backup=False,
        restore=None,
        manual=False,
        add=False,
        update=False,
        backup=False,
        list_backups=False,
        status=False,
        remove=False,
        yes=False,
        force=False,
        json=False,
        codex_home=None,
        python_executable=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def make_home(tmp_path, name="codex-home"):
    home = tmp_path / name
    home.mkdir(parents=True, exist_ok=True)
    return home


CRED = ("https://api.deepseek.com", 'experimental_bearer_token = "sk-test"', "test")


def setup_install(monkeypatch, tmp_path, cred=CRED, windows=False):
    """Fresh CODEX_HOME with credential resolution and platform stubbed."""
    home = make_home(tmp_path)
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(mod, "resolve_credentials", lambda codex_home: cred)
    monkeypatch.setattr(mod, "is_windows", lambda: windows)
    return home
