"""AGENTS.md marker blocks: create, replace, preserve unrelated lines."""

import codex_deepseek_subagent_setup as mod


def test_creates_file(tmp_path):
    assert mod.ensure_agents_md(tmp_path, dry_run=False)
    text = (tmp_path / "AGENTS.md").read_text()
    assert "<!-- codex-deepseek-subagent:start -->" in text
    assert "<!-- codex-deepseek-subagent:end -->" in text
    assert "<!-- task-handoff:start -->" in text
    assert "<!-- task-handoff:end -->" in text


def test_replaces_blocks_preserves_unrelated(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text(
        "# My notes\n"
        "<!-- codex-deepseek-subagent:start -->\n"
        "- stale routing\n"
        "<!-- codex-deepseek-subagent:end -->\n"
        "<!-- task-handoff:start -->\n"
        "- stale task block\n"
        "<!-- task-handoff:end -->\n"
        "keep me\n"
    )
    assert mod.ensure_agents_md(tmp_path, dry_run=False)
    text = target.read_text()
    assert "keep me" in text
    assert "# My notes" in text
    assert "stale routing" not in text
    assert "stale task block" not in text
    assert "prefer `v4_flash_worker`" in text


def test_partial_block_rebuilds_whole_doc(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text(
        "<!-- codex-deepseek-subagent:start -->\n- stale\n<!-- codex-deepseek-subagent:end -->\n"
    )
    mod.ensure_agents_md(tmp_path, dry_run=False)
    text = target.read_text()
    assert "<!-- task-handoff:start -->" in text


def test_appends_when_no_blocks(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text("existing content\n")
    mod.ensure_agents_md(tmp_path, dry_run=False)
    text = target.read_text()
    assert text.startswith("existing content")
    assert "<!-- codex-deepseek-subagent:start -->" in text


def test_idempotent(tmp_path):
    mod.ensure_agents_md(tmp_path, dry_run=False)
    assert not mod.ensure_agents_md(tmp_path, dry_run=False)
