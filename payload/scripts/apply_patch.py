#!/usr/bin/env python3
"""Atomic, worktree-confined unified-diff patch fallback.

The built-in ``apply_patch`` tool can fail to launch on Windows when the
Codex executable is backed by a WindowsApps shim ("Access is denied"). This
script is the supported, repo-owned fallback for ordinary implementation
files: it reads a standard unified diff from stdin and applies it inside an
explicit ``--root`` directory.

Guarantees:

- Path confinement: every target must be a relative path under ``--root``.
  Absolute paths (POSIX or Windows), drive-relative paths, ``..`` traversal,
  and any target that resolves outside ``--root`` are rejected before any
  file is touched.
- Atomicity: the whole patch is parsed, validated, and applied in memory
  first. Files are written only after every hunk applies. The write phase
  stages temporary files and backs up existing targets, so a failure restores
  every file that was already replaced.
- Encoding: the patch input and every target file must be valid UTF-8. New
  files are written with LF; modified files keep their dominant line ending
  (LF or CRLF), so CJK content and line endings stay correct.

Unsupported, rejected deterministically before any write: ``\\ No newline at
end of file`` markers, renames (old and new paths must match), binary diffs,
duplicate targets, and patches without any file section. Hunk body lines that
also match a file header (content starting with ``-- `` or ``@ ``) are
rejected by the strict hunk count validation instead of being misapplied.

Exit codes: 0 applied, 1 usage error, 2 invalid patch, 3 could not apply or
write, 10 patch input was not valid UTF-8.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from pathlib import PurePosixPath
from pathlib import PureWindowsPath
import re
import stat
import sys
import uuid


DEVNULL = "/dev/null"
HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*$")


class PatchError(ValueError):
    """The patch text is malformed or violates path constraints."""


class ApplyError(RuntimeError):
    """The patch is well-formed but cannot be applied to the worktree."""


class Hunk:
    __slots__ = ("old_start", "old_count", "new_count", "items")

    def __init__(self, old_start, old_count, new_count, items):
        self.old_start = old_start
        self.old_count = old_count
        self.new_count = new_count
        self.items = items


class FileWrite:
    __slots__ = ("operation", "target", "payload", "mode")

    def __init__(self, operation, target, payload, mode):
        self.operation = operation
        self.target = target
        self.payload = payload
        self.mode = mode


def configure_standard_streams() -> None:
    """Keep the fallback protocol UTF-8 regardless of the platform locale."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict")


def fail(message: str, code: int) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def parse_patch(text: str) -> list[tuple[str, str, list[Hunk]]]:
    """Parse a standard unified diff into (old, new, hunks) file patches."""
    raw_lines = text.splitlines()
    patches: list[tuple[str, str, list[Hunk]]] = []
    index = 0
    count = len(raw_lines)
    while index < count:
        line = raw_lines[index]
        if line.startswith("--- "):
            old_raw = _header_path(line[4:])
            index += 1
            if index >= count or not raw_lines[index].startswith("+++ "):
                raise PatchError("a '--- ' file header must be followed by a '+++ ' header")
            new_raw = _header_path(raw_lines[index][4:])
            index += 1
            hunks, index = _parse_hunks(raw_lines, index, count)
            patches.append((old_raw, new_raw, hunks))
        elif line.startswith("+++ ") or line.startswith("@@"):
            raise PatchError("'+++ ' or '@@ ' line found outside a file section")
        else:
            index += 1  # preamble: diff --git, index, mode lines, and so on.
    return patches


def _header_path(raw: str) -> str:
    """Strip a diff timestamp suffix ('\\t<timestamp>') from a file header."""
    return raw.split("\t", 1)[0].strip()


def _parse_hunks(raw_lines: list[str], index: int, count: int) -> tuple[list[Hunk], int]:
    hunks: list[Hunk] = []
    while index < count:
        line = raw_lines[index]
        if line.startswith("--- ") or line.startswith("diff --git"):
            break
        if not line.startswith("@@"):
            raise PatchError(f"unexpected line inside a file section: {line!r}")
        hunk, index = _parse_hunk(raw_lines, index, count)
        hunks.append(hunk)
    return hunks, index


def _parse_hunk(raw_lines: list[str], index: int, count: int) -> tuple[Hunk, int]:
    header = HUNK_HEADER.match(raw_lines[index])
    if header is None:
        raise PatchError(f"malformed hunk header: {raw_lines[index]!r}")
    old_start = int(header.group(1))
    old_count = int(header.group(2) or "1")
    new_count = int(header.group(4) or "1")
    items: list[tuple[str, str]] = []
    old_total = 0
    new_total = 0
    index += 1
    while index < count:
        line = raw_lines[index]
        if line.startswith("@@") or line.startswith("--- ") or line.startswith("diff --git"):
            break
        if line.startswith("\\ "):
            raise PatchError(
                "'\\ No newline at end of file' markers are not supported; "
                "ensure the file ends with a newline"
            )
        if line == "":
            kind, text = " ", ""
        elif line.startswith(" "):
            kind, text = " ", line[1:]
        elif line.startswith("-"):
            kind, text = "-", line[1:]
        elif line.startswith("+"):
            kind, text = "+", line[1:]
        else:
            raise PatchError(f"malformed hunk body line: {line!r}")
        items.append((kind, text))
        if kind in (" ", "-"):
            old_total += 1
        if kind in (" ", "+"):
            new_total += 1
        index += 1
    if not items and not (old_count == 0 and new_count == 0):
        raise PatchError(f"hunk {raw_lines[index - 1]!r} has an empty body")
    if old_total != old_count or new_total != new_count:
        raise PatchError(
            f"hunk body line counts ({old_total}, {new_total}) do not match "
            f"the header ({old_count}, {new_count})"
        )
    return Hunk(old_start, old_count, new_count, items), index


def resolve_target(old_raw: str, new_raw: str) -> tuple[str, str]:
    """Resolve the operation and relative target from a file header pair."""
    old_devnull = old_raw == DEVNULL
    new_devnull = new_raw == DEVNULL
    if old_devnull and new_devnull:
        raise PatchError("both file headers reference /dev/null")
    if old_devnull:
        return "create", _strip_diff_prefix(new_raw)
    if new_devnull:
        return "delete", _strip_diff_prefix(old_raw)
    old_has_prefix = _has_diff_prefix(old_raw)
    new_has_prefix = _has_diff_prefix(new_raw)
    if old_has_prefix != new_has_prefix:
        raise PatchError("inconsistent 'a/' 'b/' prefixes in the file headers")
    old_target = _strip_diff_prefix(old_raw)
    new_target = _strip_diff_prefix(new_raw)
    if old_target != new_target:
        raise PatchError("renames are not supported: old and new paths differ")
    return "modify", old_target


def _has_diff_prefix(path: str) -> bool:
    return path.startswith(("a/", "b/"))


def _strip_diff_prefix(path: str) -> str:
    return path[2:] if _has_diff_prefix(path) else path


def confine_target(target_raw: str, root: Path) -> Path:
    """Reject absolute, traversing, or root-escaping targets; return the target."""
    normalized = target_raw.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(normalized)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or windows.root:
        raise PatchError(f"absolute paths are not allowed: {target_raw!r}")
    parts = posix.parts
    if not parts or any(part == ".." for part in parts):
        raise PatchError(f"path traversal is not allowed: {target_raw!r}")
    root_resolved = root.resolve()
    candidate = root_resolved.joinpath(*parts)
    resolved = candidate.resolve()
    if resolved != root_resolved and not resolved.is_relative_to(root_resolved):
        raise PatchError(f"target escapes the worktree root: {target_raw!r}")
    return resolved


def detect_line_ending(payload: bytes) -> str:
    """Pick the newline convention that dominates the given byte payload."""
    crlf_count = payload.count(b"\r\n")
    lf_count = payload.count(b"\n") - crlf_count
    return "\r\n" if crlf_count > lf_count else "\n"


def split_logical_lines(text: str) -> tuple[list[str], bool]:
    """Split text into logical lines and report whether it ends with a newline."""
    if text == "":
        return [], False
    ends_with_newline = text.endswith("\n")
    raw = text.split("\n")
    if ends_with_newline:
        raw.pop()
    lines = [line[:-1] if line.endswith("\r") else line for line in raw]
    return lines, ends_with_newline


def join_logical_lines(lines: list[str], ends_with_newline: bool, ending: str) -> str:
    joined = ending.join(lines)
    if ends_with_newline:
        return joined + ending
    return joined


def apply_hunk(lines: list[str], hunk: Hunk) -> list[str]:
    """Apply one hunk at its stated position with exact context matching."""
    if hunk.old_count == 0:
        # Pure-insertion hunk: the old line number is the zero-based insertion
        # point (0 = before the first line), matching `git diff -U0` output.
        # It is not a 1-based line number, so there is no -1 offset.
        position = hunk.old_start
    else:
        position = hunk.old_start - 1
    if position > len(lines) or (
        hunk.old_count > 0 and position + hunk.old_count > len(lines)
    ):
        raise ApplyError(
            f"hunk at line {hunk.old_start} does not apply: target lines are out of range"
        )
    output: list[str] = []
    index = position
    for kind, text in hunk.items:
        if kind in (" ", "-"):
            if index >= len(lines) or lines[index] != text:
                raise ApplyError(
                    f"hunk at line {hunk.old_start} does not apply: context does not match"
                )
            index += 1
            if kind == " ":
                output.append(text)
        else:
            output.append(text)
    return lines[:position] + output + lines[index:]


def decode_target(payload: bytes, target_raw: str) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ApplyError(f"target file is not valid UTF-8: {target_raw!r}") from error


def apply_file_patch(
    hunks: list[Hunk], lines: list[str], ends_with_newline: bool, ending: str
) -> bytes:
    """Apply every hunk bottom-up (positions refer to the original file)."""
    for hunk in reversed(hunks):
        lines = apply_hunk(lines, hunk)
    return join_logical_lines(lines, ends_with_newline, ending).encode("utf-8")


def build_writes(root: Path, patches) -> list[FileWrite]:
    """Validate and apply the whole patch in memory; nothing is written here."""
    writes: list[FileWrite] = []
    seen: set[Path] = set()
    for old_raw, new_raw, hunks in patches:
        operation, target_raw = resolve_target(old_raw, new_raw)
        target = confine_target(target_raw, root)
        if target in seen:
            raise PatchError(f"duplicate target in patch: {target_raw!r}")
        seen.add(target)
        if operation == "create":
            if target.exists():
                raise ApplyError(f"cannot create an existing file: {target_raw!r}")
            if any(hunk.new_count > 0 for hunk in hunks):
                payload = apply_file_patch(hunks, [], True, "\n")
            else:
                # Empty-file creation: `--- /dev/null` plus `+++ <path>` with
                # no hunks (or only a no-op `@@ -0,0 +0,0 @@` hunk) writes a
                # zero-byte file.
                payload = b""
            writes.append(FileWrite("create", target, payload, None))
        elif operation == "delete":
            if not target.exists():
                raise ApplyError(f"cannot delete a missing file: {target_raw!r}")
            payload_bytes = target.read_bytes()
            lines, ends_with_newline = split_logical_lines(
                decode_target(payload_bytes, target_raw)
            )
            if not hunks and lines:
                raise PatchError(
                    f"delete section for {target_raw!r} has no hunks but "
                    "the target is not empty"
                )
            apply_file_patch(
                hunks, lines, ends_with_newline, detect_line_ending(payload_bytes)
            )
            writes.append(FileWrite("delete", target, None, None))
        else:
            if not target.exists():
                raise ApplyError(f"cannot modify a missing file: {target_raw!r}")
            if not hunks:
                raise PatchError(f"modify section for {target_raw!r} has no hunks")
            payload_bytes = target.read_bytes()
            lines, ends_with_newline = split_logical_lines(
                decode_target(payload_bytes, target_raw)
            )
            payload = apply_file_patch(
                hunks, lines, ends_with_newline, detect_line_ending(payload_bytes)
            )
            writes.append(
                FileWrite("modify", target, payload, target.stat().st_mode)
            )
    return writes


def commit_writes(writes: list[FileWrite]) -> None:
    """Stage temps, back up targets, replace, and roll back on any failure."""
    staged: list[tuple[Path, Path]] = []
    backups: dict[Path, Path] = {}
    touched: list[Path] = []
    try:
        for item in writes:
            if item.operation == "delete":
                continue
            item.target.parent.mkdir(parents=True, exist_ok=True)
            temporary = item.target.with_name(
                f".{item.target.name}.{uuid.uuid4().hex}.tmp"
            )
            with temporary.open("wb") as stream:
                stream.write(item.payload)
                stream.flush()
                os.fsync(stream.fileno())
            if item.mode is not None:
                os.chmod(temporary, item.mode)
            staged.append((temporary, item.target))
        for item in writes:
            if item.target.exists():
                backup = item.target.with_name(
                    f".{item.target.name}.{uuid.uuid4().hex}.bak"
                )
                backup.write_bytes(item.target.read_bytes())
                backups[item.target] = backup
        for temporary, target in staged:
            os.replace(temporary, target)
            touched.append(target)
        for item in writes:
            if item.operation == "delete" and item.target.exists():
                os.unlink(item.target)
                touched.append(item.target)
    except OSError as error:
        for target in reversed(touched):
            backup = backups.get(target)
            if backup is not None and backup.exists():
                try:
                    os.replace(backup, target)
                except OSError:
                    pass
        raise
    finally:
        for temporary, _ in staged:
            _best_effort_remove(temporary)
        for backup in backups.values():
            _best_effort_remove(backup)


def _best_effort_remove(path: Path) -> None:
    try:
        os.chmod(path, os.stat(path).st_mode | stat.S_IWRITE)
    except OSError:
        pass
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def main() -> None:
    configure_standard_streams()
    parser = argparse.ArgumentParser(
        description=(
            "Apply a standard unified diff atomically inside a worktree root."
        )
    )
    parser.add_argument(
        "--root",
        required=True,
        help=(
            "Absolute path to the worktree root that every patched target "
            "must stay inside."
        ),
    )
    arguments = parser.parse_args()
    root = Path(arguments.root).expanduser().resolve()
    if not root.is_dir():
        fail(f"The --root path is not a directory: {root}", 1)
    try:
        patch_text = sys.stdin.read()
    except UnicodeError as error:
        fail(f"The patch input was not valid UTF-8. ({error})", 10)
    try:
        patches = parse_patch(patch_text)
        if not patches:
            raise PatchError("the patch input contains no file sections")
        writes = build_writes(root, patches)
        commit_writes(writes)
    except PatchError as error:
        fail(f"Invalid patch: {error}", 2)
    except ApplyError as error:
        fail(str(error), 3)
    except OSError as error:
        fail(f"Could not write the patch: {error}", 3)


if __name__ == "__main__":
    main()