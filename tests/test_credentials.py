"""Credential resolution: preserve, interactive override, fallbacks."""

import sys

import codex_deepseek_subagent_setup as mod


def resolve(monkeypatch, codex_home, isatty, kimi, inputs):
    monkeypatch.setattr(mod, "load_opencode_go_credentials", lambda: kimi)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: isatty)
    if isatty:
        it = iter(inputs)
        monkeypatch.setattr("builtins.input", lambda *a, **k: next(it))
    return mod.resolve_credentials(codex_home)


def test_fresh_home_falls_back_to_env_key(tmp_path, monkeypatch):
    base, lines, source = resolve(monkeypatch, tmp_path / "home", False, (None, None), [])
    assert base == "https://api.deepseek.com"
    assert lines == 'env_key = "DEEPSEEK_API_KEY"'
    assert "env var" in source


def test_non_tty_uses_kimi(tmp_path, monkeypatch):
    base, lines, source = resolve(
        monkeypatch, tmp_path / "home", False, ("https://kimi.example", "sk-kimi"), []
    )
    assert base == "https://kimi.example"
    assert 'experimental_bearer_token = "sk-kimi"' in lines
    assert "kimi" in source


def test_preserves_existing_token_noninteractive(tmp_path, monkeypatch):
    home = tmp_path / "home"
    agent = home / "agents" / "v4-flash-worker.toml"
    agent.parent.mkdir(parents=True)
    agent.write_text(
        'name = "v4_flash_worker"\n'
        "[model_providers.deepseek]\n"
        'base_url = "https://preserved.example"\n'
        'experimental_bearer_token = "sk-existing"\n',
        encoding="utf-8",
    )
    base, lines, source = resolve(
        monkeypatch, home, False, ("https://kimi.example", "sk-kimi"), []
    )
    assert base == "https://preserved.example"
    assert lines == 'experimental_bearer_token = "sk-existing"'
    assert "preserved" in source


def test_interactive_override_wins_over_existing(tmp_path, monkeypatch):
    home = tmp_path / "home"
    agent = home / "agents" / "v4-flash-worker.toml"
    agent.parent.mkdir(parents=True)
    agent.write_text(
        'name = "v4_flash_worker"\n'
        "[model_providers.deepseek]\n"
        'experimental_bearer_token = "sk-old"\n',
        encoding="utf-8",
    )
    base, lines, source = resolve(
        monkeypatch, home, True, (None, None), ["https://x.example", "sk-new"]
    )
    assert base == "https://x.example"
    assert lines == 'experimental_bearer_token = "sk-new"'
    assert "user input" in source
