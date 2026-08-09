"""config.toml [shell_environment_policy.set]: merge, preserve, remove."""

import tomllib

import codex_deepseek_subagent_setup as mod


def test_merge_config_creates_section():
    new, changed = mod.merge_config("")
    assert changed
    assert mod.CONFIG_SECTION in new
    assert 'PYTHONUTF8 = "1"' in new
    assert 'PYTHONIOENCODING = "utf-8"' in new


def test_merge_config_preserves_unrelated():
    text = 'model = "gpt-5.6-sol"\n\n[features]\njs_repl = false\n'
    new, changed = mod.merge_config(text)
    assert changed
    assert 'model = "gpt-5.6-sol"' in new
    assert "[features]" in new
    assert "js_repl = false" in new
    data = tomllib.loads(new)
    assert data["features"]["js_repl"] is False
    assert data["shell_environment_policy"]["set"]["PYTHONUTF8"] == "1"


def test_merge_config_unchanged():
    text = (
        "[shell_environment_policy.set]\n"
        'PYTHONUTF8 = "1"\n'
        'PYTHONIOENCODING = "utf-8"\n'
    )
    new, changed = mod.merge_config(text)
    assert not changed
    assert new == text


def test_merge_config_fixes_wrong_values():
    text = "[shell_environment_policy.set]\nPYTHONUTF8 = \"0\"\n"
    new, changed = mod.merge_config(text)
    assert changed
    assert 'PYTHONUTF8 = "1"' in new
    assert 'PYTHONIOENCODING = "utf-8"' in new


def test_remove_config_preserves_user_table(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    config = home / "config.toml"
    config.write_text(
        "[shell_environment_policy.set]\n"
        'PYTHONUTF8 = "1"\n'
        'PYTHONIOENCODING = "utf-8"\n'
        "\n[features]\nuser_thing = true\n",
        encoding="utf-8",
    )
    assert mod.remove_config_owned(home, {}, dry_run=False) == "update"
    data = tomllib.loads(config.read_text())
    assert "shell_environment_policy" not in data
    assert data["features"]["user_thing"] is True


def test_remove_config_keeps_header_when_user_key_present(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    config = home / "config.toml"
    config.write_text(
        "[shell_environment_policy.set]\n"
        'PYTHONUTF8 = "1"\n'
        'USER_KEY = "keep"\n',
        encoding="utf-8",
    )
    assert mod.remove_config_owned(home, {}, dry_run=False) == "update"
    text = config.read_text()
    assert mod.CONFIG_SECTION in text
    assert 'PYTHONUTF8 = "1"' not in text
    assert 'USER_KEY = "keep"' in text


def test_remove_config_deletes_owned_file(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    config = home / "config.toml"
    config.write_text(
        "[shell_environment_policy.set]\n"
        'PYTHONUTF8 = "1"\n'
        'PYTHONIOENCODING = "utf-8"\n',
        encoding="utf-8",
    )
    state = {"files": {"config.toml": mod.sha256_of(config)}}
    assert mod.remove_config_owned(home, state, dry_run=False) == "delete"
    assert not config.exists()


def test_remove_config_noop_without_owned_keys(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    config = home / "config.toml"
    config.write_text('model = "x"\n', encoding="utf-8")
    assert mod.remove_config_owned(home, {}, dry_run=False) == "noop"
    assert config.read_text() == 'model = "x"\n'
