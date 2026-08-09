"""AGENTS.md block sync, legacy migration, and surgical removal."""

import codex_deepseek_subagent_setup as mod


def block():
    return mod.agents_block_text()


def test_merge_creates_block():
    text, changed = mod.merge_agents("", block())
    assert changed
    assert f"<!-- {mod.AGENTS_BLOCK_MARKER}:start -->" in text
    assert text.count(f"<!-- {mod.AGENTS_BLOCK_MARKER}:start -->") == 1


def test_merge_migrates_legacy_marker():
    legacy = (
        "<!-- codex-deepseek-subagent:start -->\n"
        "legacy routing\n"
        "<!-- codex-deepseek-subagent:end -->\n"
    )
    unrelated = "# user\nkeep\n"
    text, changed = mod.merge_agents(legacy + "\n" + unrelated, block())
    assert changed
    assert "<!-- codex-deepseek-subagent:start -->" not in text
    assert text.count(f"<!-- {mod.AGENTS_BLOCK_MARKER}:start -->") == 1
    assert "keep" in text


def test_merge_preserves_unrelated_content():
    existing = "# my rules\n\n- keep\n"
    text, changed = mod.merge_agents(existing, block())
    assert changed
    assert text.startswith("# my rules")
    assert "- keep" in text


def test_merge_idempotent():
    text, _ = mod.merge_agents("", block())
    again, changed = mod.merge_agents(text, block())
    assert not changed
    assert again == text


def test_remove_block_preserves_unrelated(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    target = home / "AGENTS.md"
    merged, _ = mod.merge_agents("", block())
    target.write_text(merged + "# user section\nkeep-me\n", encoding="utf-8")
    assert mod.remove_agents_block(home, {}, dry_run=False) == "update"
    text = target.read_text()
    assert "codex-v4-flash-worker-agents" not in text
    assert "keep-me" in text


def test_remove_block_deletes_owned_file(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    target = home / "AGENTS.md"
    merged, _ = mod.merge_agents("", block())
    target.write_text(merged, encoding="utf-8")
    state = {"files": {"AGENTS.md": mod.sha256_of(target)}}
    assert mod.remove_agents_block(home, state, dry_run=False) == "delete"
    assert not target.exists()
