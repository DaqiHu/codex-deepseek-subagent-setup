"""The installer never reads or writes ~/.agents at runtime."""

import pathlib

import codex_deepseek_subagent_setup as mod
from conftest import make_args, setup_install


def test_install_never_touches_agents_dir(tmp_path, monkeypatch, capsys):
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: fake_home))
    home = setup_install(monkeypatch, tmp_path)
    backup_root = tmp_path / "backups"
    assert mod.cmd_install(make_args(backup_dir=str(backup_root))) == 0
    assert not (fake_home / ".agents").exists()
    assert not (fake_home / ".codex").exists()
    assert not (fake_home / ".kimi-code").exists()
    for rel in mod.MANAGED_FILES:
        assert (home / rel).exists()


def test_no_agents_path_literal_in_runtime_code():
    source = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    begin = source.find("# BEGIN AUTO-GENERATED PAYLOAD")
    end = source.find("# END AUTO-GENERATED PAYLOAD")
    code = source[:begin] + source[end:]
    assert '".agents"' not in code
    assert "~/.agents" not in code
