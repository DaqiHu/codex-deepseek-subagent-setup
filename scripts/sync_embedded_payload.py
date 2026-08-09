#!/usr/bin/env python3
"""Sync the canonical payload/ tree into the single-file installer.

The repository keeps the authoritative Codex v4_flash_worker skill payload
under payload/ (mirroring ~/.agents/codex/skills/use-v4-flash-worker). The
single raw-script `uv run <url>` path cannot read payload/ from disk, so this
script embeds a byte-exact base64 copy plus a per-file SHA-256 manifest into
codex_deepseek_subagent_setup.py between the AUTO-GENERATED PAYLOAD markers.

Usage:
    python scripts/sync_embedded_payload.py                 # embed payload/
    python scripts/sync_embedded_payload.py --source <dir>  # copy canonical files
                                                             # from <dir> first, then embed
    python scripts/sync_embedded_payload.py --check         # read-only parity check;
                                                             # exits nonzero on drift

A parity test (tests/test_payload.py) fails when payload/ and the embedded
copy drift, so the repo stays the single source of truth. ``--check`` performs
the same comparison without writing anything: it regenerates the embedded block
from payload/ + pyproject.toml and exits 1 when the installer file would
change (payload drift, manual edits to the embedded block, or version drift).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import pathlib
import py_compile
import sys
import tomllib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "codex_deepseek_subagent_setup.py"
PAYLOAD_DIR = REPO_ROOT / "payload"

# payload rel path -> destination relative to the installed skill dir
PAYLOAD_FILES = (
    "SKILL.md",
    "agents/codex_AGENTS_block.md",
    "agents/openai.yaml",
    "scripts/plaintext_handoff.py",
    "scripts/update_task_result.py",
    "scripts/apply_patch.py",
    "scripts/install.py",
)

BEGIN_MARKER = "# BEGIN AUTO-GENERATED PAYLOAD"
END_MARKER = "# END AUTO-GENERATED PAYLOAD"


def read_version() -> str:
    with (REPO_ROOT / "pyproject.toml").open("rb") as stream:
        data = tomllib.load(stream)
    return data["project"]["version"]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render_block(version: str, manifest: dict[str, str], blobs: dict[str, bytes]) -> str:
    manifest_lines = ",\n".join(
        f'    "{rel}": "{digest}"' for rel, digest in manifest.items()
    )
    blob_lines = ",\n".join(
        f'    "{rel}": "{base64.b64encode(data).decode("ascii")}"'
        for rel, data in blobs.items()
    )
    return (
        f"{BEGIN_MARKER} (managed by scripts/sync_embedded_payload.py)\n"
        "# Do not edit by hand: change payload/ and re-run the sync script.\n"
        f'PAYLOAD_VERSION = "{version}"\n'
        "PAYLOAD_MANIFEST = {\n"
        f"{manifest_lines}\n"
        "}\n"
        "_PAYLOAD_B64 = {\n"
        f"{blob_lines}\n"
        "}\n"
        f"{END_MARKER}\n"
    )


def read_payload() -> dict[str, bytes]:
    blobs: dict[str, bytes] = {}
    for rel in PAYLOAD_FILES:
        blobs[rel] = (PAYLOAD_DIR / rel).read_bytes()
    return blobs


def check_drift() -> list[str]:
    """Return drift problems; empty means payload/, embed, and version match.

    Read-only: compares the embedded block against what the sync would write
    without touching any file.
    """
    problems: list[str] = []
    try:
        source = INSTALLER.read_text(encoding="utf-8")
    except OSError as error:
        return [f"cannot read {INSTALLER}: {error}"]
    try:
        blobs = read_payload()
    except OSError as error:
        return [f"cannot read payload tree under {PAYLOAD_DIR}: {error}"]
    manifest = {rel: sha256_bytes(data) for rel, data in blobs.items()}
    try:
        block = render_block(read_version(), manifest, blobs)
        updated = replace_embedded_block(source, block)
    except SystemExit as error:
        return [str(error)]
    if updated != source:
        problems.append(
            "payload/ or pyproject version drifted from the embedded copy; "
            "re-run scripts/sync_embedded_payload.py"
        )
    return problems


def replace_embedded_block(source: str, block: str) -> str:
    start = source.find(BEGIN_MARKER)
    end = source.find(END_MARKER)
    if start < 0 or end < 0:
        raise SystemExit(
            f"cannot find {BEGIN_MARKER} / {END_MARKER} markers in {INSTALLER}"
        )
    end_of_line = source.find("\n", end)
    if end_of_line < 0:
        end_of_line = len(source)
    else:
        end_of_line += 1
    return source[:start] + block + source[end_of_line:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        help="optional canonical skill directory to copy payload files from first",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify payload/embed/version parity read-only; exit nonzero on drift",
    )
    args = parser.parse_args()

    if args.check:
        problems = check_drift()
        for problem in problems:
            print(f"CHECK FAIL: {problem}")
        if not problems:
            print("check: payload/, embedded copy, and pyproject version are in sync")
        return 1 if problems else 0

    if args.source:
        source_root = pathlib.Path(args.source).expanduser().resolve()
        if not source_root.is_dir():
            raise SystemExit(f"--source is not a directory: {source_root}")
        for rel in PAYLOAD_FILES:
            source = source_root / rel
            if not source.is_file():
                raise SystemExit(f"missing canonical file in {source_root}: {rel}")
            destination = PAYLOAD_DIR / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            print(f"copied {source} -> {destination}")

    blobs = read_payload()
    manifest = {rel: sha256_bytes(data) for rel, data in blobs.items()}
    block = render_block(read_version(), manifest, blobs)
    source = INSTALLER.read_text(encoding="utf-8")
    updated = replace_embedded_block(source, block)
    INSTALLER.write_text(updated, encoding="utf-8", newline="\n")
    py_compile.compile(str(INSTALLER), doraise=True)
    print(f"embedded {len(blobs)} payload files into {INSTALLER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
