"""Credential resolution: interactive override, auto-fallback, non-TTY."""

import sys

import codex_deepseek_subagent_setup as mod


def resolve(monkeypatch, isatty, kimi, inputs):
    monkeypatch.setattr(mod, "load_opencode_go_credentials", lambda: kimi)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: isatty)
    if isatty:
        it = iter(inputs)
        monkeypatch.setattr("builtins.input", lambda *a, **k: next(it))
    return mod.resolve_credentials()


def test_non_tty_uses_kimi(monkeypatch):
    base, lines, source = resolve(
        monkeypatch, False, ("https://kimi.example", "sk-kimi"), []
    )
    assert base == "https://kimi.example"
    assert 'experimental_bearer_token = "sk-kimi"' in lines
    assert "kimi" in source


def test_non_tty_falls_back_to_env_key(monkeypatch):
    base, lines, source = resolve(monkeypatch, False, (None, None), [])
    assert base == "https://api.deepseek.com"
    assert lines == 'env_key = "DEEPSEEK_API_KEY"'
    assert "env var" in source


def test_tty_override_both(monkeypatch):
    base, lines, source = resolve(
        monkeypatch, True, (None, None), ["https://x.example", "sk-user"]
    )
    assert base == "https://x.example"
    assert 'experimental_bearer_token = "sk-user"' in lines
    assert "user input" in source


def test_tty_empty_falls_back_to_kimi(monkeypatch):
    base, lines, source = resolve(
        monkeypatch, True, ("https://kimi.example", "sk-kimi"), ["", ""]
    )
    assert base == "https://kimi.example"
    assert 'experimental_bearer_token = "sk-kimi"' in lines


def test_tty_partial_override_base_only(monkeypatch):
    base, lines, source = resolve(
        monkeypatch, True, ("https://kimi.example", "sk-kimi"), ["https://y.example", ""]
    )
    assert base == "https://y.example"
    assert 'experimental_bearer_token = "sk-kimi"' in lines
