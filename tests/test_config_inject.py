"""config.toml [features.multi_agent_v2] injection: append/update/unchanged."""

import tomllib

import codex_deepseek_subagent_setup as mod


def test_append_block(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('model = "gpt-5.6-sol"\n\n[features]\njs_repl = false\n')
    assert mod.ensure_features_multi_agent_v2(config, dry_run=False)
    data = tomllib.loads(config.read_text())
    assert data["features"]["multi_agent_v2"] == {
        "hide_spawn_agent_metadata": False,
        "tool_namespace": "agents",
    }
    assert data["model"] == "gpt-5.6-sol"


def test_update_wrong_values(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        "[features.multi_agent_v2]\n"
        'hide_spawn_agent_metadata = true\n'
        'tool_namespace = "tools"\n'
    )
    assert mod.ensure_features_multi_agent_v2(config, dry_run=False)
    data = tomllib.loads(config.read_text())
    assert data["features"]["multi_agent_v2"]["hide_spawn_agent_metadata"] is False
    assert data["features"]["multi_agent_v2"]["tool_namespace"] == "agents"


def test_unchanged(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        "[features.multi_agent_v2]\n"
        "hide_spawn_agent_metadata = false\n"
        'tool_namespace = "agents"\n'
    )
    assert not mod.ensure_features_multi_agent_v2(config, dry_run=False)


def test_missing_file_skips(tmp_path):
    assert not mod.ensure_features_multi_agent_v2(
        tmp_path / "config.toml", dry_run=False
    )


def test_dry_run_writes_nothing(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('model = "gpt-5.6-sol"\n')
    mod.ensure_features_multi_agent_v2(config, dry_run=True)
    assert "[features.multi_agent_v2]" not in config.read_text()
