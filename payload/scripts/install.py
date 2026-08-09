#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any
import uuid


AGENT_TYPE = "v4_flash_worker"
AGENTS_BLOCK_MARKER = "codex-v4-flash-worker-agents"
LEGACY_AGENTS_BLOCK_MARKER = "codex-deepseek-subagent"
AGENTS_BLOCK_ASSET = Path("agents") / "codex_AGENTS_block.md"
ENVIRONMENT_VALUES = {
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
}
# Codex docs: omit additionalContextLimit for the 2500-token default, use a
# positive threshold, or keep 0 only when the hook enforces a strict output cap.
# plaintext_handoff.py enforces MAX_ASSIGNMENT_BYTES_DEFAULT at stage time, so 0
# is safe here and delivers the complete contract without a truncated preview.
# timeout: the documented default for most hooks is 600s; 60s is a generous
# bound for a fast local file read while still failing fast on a hung Hook.
HOOK_TIMEOUT_SECONDS = 60
HOOK_ADDITIONAL_CONTEXT_LIMIT = 0


def write_bytes_atomically(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def copy_file(source: Path, destination: Path) -> None:
    write_bytes_atomically(destination, source.read_bytes())


def load_agents_block(source_root: Path) -> str:
    """Read the version-controlled marked Codex AGENTS block asset."""
    text = (source_root / AGENTS_BLOCK_ASSET).read_text(encoding="utf-8")
    start_marker = f"<!-- {AGENTS_BLOCK_MARKER}:start -->"
    end_marker = f"<!-- {AGENTS_BLOCK_MARKER}:end -->"
    start_index = text.find(start_marker)
    end_index = text.find(end_marker, start_index)
    if start_index < 0 or end_index < 0:
        raise ValueError(
            f"{AGENTS_BLOCK_ASSET} must contain both {AGENTS_BLOCK_MARKER} markers"
        )
    end_of_line = text.find("\n", end_index)
    if end_of_line < 0:
        end_of_line = len(text)
    else:
        end_of_line += 1
    block = text[start_index:end_of_line]
    if not block.endswith("\n"):
        block += "\n"
    return block


def sync_agents_block(agents_path: Path, block: str) -> bool:
    """Idempotently merge the marked block into ~/.codex/AGENTS.md.

    Migrates a legacy codex-deepseek-subagent marker region (removing it in
    full), then replaces the region between the new markers when present or
    appends the block otherwise. Content outside the marked blocks is
    preserved byte-for-byte. Returns True when the file was written.
    """
    existing = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
    existing = _strip_legacy_agents_block(existing, agents_path)
    start_marker = f"<!-- {AGENTS_BLOCK_MARKER}:start -->"
    end_marker = f"<!-- {AGENTS_BLOCK_MARKER}:end -->"
    start_index = existing.find(start_marker)
    if start_index >= 0:
        end_index = existing.find(end_marker, start_index)
        if end_index < 0:
            raise ValueError(
                f"{agents_path} has a dangling {AGENTS_BLOCK_MARKER} start marker"
            )
        end_of_line = existing.find("\n", end_index)
        if end_of_line < 0:
            end_of_line = len(existing)
        else:
            end_of_line += 1
        before = existing[:start_index]
        after = existing[end_of_line:]
        if before and not before.endswith("\n"):
            before += "\n"
        while after.startswith("\n"):
            after = after[1:]
        merged = before + block + after
    else:
        merged = existing
        if merged and not merged.endswith("\n"):
            merged += "\n"
        merged += block
    if merged == existing:
        return False
    write_bytes_atomically(agents_path, merged.encode("utf-8"))
    return True


def _strip_legacy_agents_block(existing: str, agents_path: Path) -> str:
    """Remove every complete legacy codex-deepseek-subagent marker region.

    The removed region spans the start marker line through the end marker
    line, inclusive. Adjacent blank lines left by the removal are collapsed.
    A dangling start marker (no matching end marker) is an error because the
    legacy block owns a contiguous region that cannot be safely identified.
    """
    start_marker = f"<!-- {LEGACY_AGENTS_BLOCK_MARKER}:start -->"
    end_marker = f"<!-- {LEGACY_AGENTS_BLOCK_MARKER}:end -->"
    while True:
        start_index = existing.find(start_marker)
        if start_index < 0:
            return existing
        end_index = existing.find(end_marker, start_index)
        if end_index < 0:
            raise ValueError(
                f"{agents_path} has a dangling {LEGACY_AGENTS_BLOCK_MARKER} start marker"
            )
        end_of_line = existing.find("\n", end_index)
        if end_of_line < 0:
            end_of_line = len(existing)
        else:
            end_of_line += 1
        before = existing[:start_index]
        after = existing[end_of_line:]
        if before and not before.endswith("\n"):
            before += "\n"
        while after.startswith("\n"):
            after = after[1:]
        existing = before + after


def configure_environment(config_path: Path) -> None:
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    lines = text.splitlines()
    section = "[shell_environment_policy.set]"
    try:
        section_index = next(index for index, line in enumerate(lines) if line.strip() == section)
    except StopIteration:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(section)
        section_index = len(lines) - 1

    end_index = len(lines)
    for index in range(section_index + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end_index = index
            break

    for key, value in ENVIRONMENT_VALUES.items():
        replacement = f'{key} = "{value}"'
        found = None
        for index in range(section_index + 1, end_index):
            if lines[index].split("=", 1)[0].strip() == key:
                found = index
                break
        if found is not None:
            lines[found] = replacement
        else:
            lines.insert(end_index, replacement)
            end_index += 1

    write_bytes_atomically(config_path, ("\n".join(lines).rstrip() + "\n").encode("utf-8"))


def load_hooks(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "description": "One-shot plaintext task handoff for the DeepSeek-backed v4_flash_worker.",
            "hooks": {},
        }
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict) or not isinstance(value.get("hooks"), dict):
        raise ValueError(f"{path} must contain a top-level JSON object with a hooks object")
    return value


def configure_hook(
    hooks_path: Path,
    hook_script: Path,
    python_executable: str,
) -> bool:
    document = load_hooks(hooks_path)
    groups = document["hooks"].setdefault("SubagentStart", [])
    if not isinstance(groups, list):
        raise ValueError("hooks.SubagentStart must be a JSON array")

    posix_command = (
        f"python3 -X utf8 {shlex.quote(str(hook_script))} --mode hook"
    )
    windows_command = subprocess.list2cmdline(
        [python_executable, "-X", "utf8", str(hook_script), "--mode", "hook"]
    )
    replacement = {
        "matcher": f"^{AGENT_TYPE}$",
        "hooks": [
            {
                "type": "command",
                "command": posix_command,
                "commandWindows": windows_command,
                "timeout": HOOK_TIMEOUT_SECONDS,
                "statusMessage": "Delivering the staged Flash assignment",
                "additionalContextLimit": HOOK_ADDITIONAL_CONTEXT_LIMIT,
            }
        ],
    }
    previous = None
    for index, group in enumerate(groups):
        if isinstance(group, dict) and group.get("matcher") == replacement["matcher"]:
            previous = group
            groups[index] = replacement
            break
    else:
        groups.append(replacement)

    payload = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    write_bytes_atomically(hooks_path, payload)
    return previous != replacement


def install_skill(source_root: Path, codex_home: Path) -> None:
    destination = codex_home / "skills" / source_root.name
    for relative in (
        Path("SKILL.md"),
        Path("agents") / "openai.yaml",
        AGENTS_BLOCK_ASSET,
        Path("scripts") / "plaintext_handoff.py",
        Path("scripts") / "update_task_result.py",
        Path("scripts") / "apply_patch.py",
        Path("scripts") / "install.py",
    ):
        copy_file(source_root / relative, destination / relative)


def install(codex_home: Path, python_executable: str) -> dict[str, Any]:
    source_root = Path(__file__).resolve().parents[1]
    hook_script = codex_home / "hooks" / "codex-deepseek-subagent" / "plaintext_handoff.py"
    copy_file(source_root / "scripts" / "plaintext_handoff.py", hook_script)
    install_skill(source_root, codex_home)
    agents_block_updated = sync_agents_block(
        codex_home / "AGENTS.md", load_agents_block(source_root)
    )
    configure_environment(codex_home / "config.toml")
    hook_changed = configure_hook(codex_home / "hooks.json", hook_script, python_executable)
    return {
        "installed": True,
        "codex_home": str(codex_home),
        "hook_script": str(hook_script),
        "python_executable": python_executable,
        "hook_definition_changed": hook_changed,
        "hook_review_required": hook_changed,
        "agents_block_updated": agents_block_updated,
    }


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--codex-home",
        default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")),
    )
    parser.add_argument("--python-executable", default=sys.executable)
    arguments = parser.parse_args()
    result = install(
        Path(arguments.codex_home).expanduser().resolve(),
        str(Path(arguments.python_executable).expanduser().resolve()),
    )
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
