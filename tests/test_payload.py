"""Payload integrity: embedded manifest, payload/ parity, optional landed parity."""

import hashlib
import pathlib
import tomllib

import pytest

import codex_deepseek_subagent_setup as mod

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD_DIR = REPO_ROOT / "payload"
LANDED_SKILL = pathlib.Path.home() / ".agents" / "codex" / "skills" / "use-v4-flash-worker"


def payload_files():
    return list(mod.PAYLOAD_MANIFEST)


def test_manifest_matches_embedded_content():
    for rel, digest in mod.PAYLOAD_MANIFEST.items():
        data = mod.payload_bytes(rel)
        assert hashlib.sha256(data).hexdigest() == digest, rel


def test_embedded_matches_payload_tree():
    for rel in payload_files():
        assert (PAYLOAD_DIR / rel).read_bytes() == mod.payload_bytes(rel), rel


def test_payload_is_lf():
    for rel in payload_files():
        assert b"\r\n" not in mod.payload_bytes(rel), rel


def test_payload_version_matches_pyproject():
    with (REPO_ROOT / "pyproject.toml").open("rb") as stream:
        version = tomllib.load(stream)["project"]["version"]
    assert mod.PAYLOAD_VERSION == version


@pytest.mark.skipif(not LANDED_SKILL.is_dir(), reason="authoritative skill tree not present")
def test_payload_parity_with_landed_skill():
    for rel in payload_files():
        assert (LANDED_SKILL / rel).read_bytes() == mod.payload_bytes(rel), rel
