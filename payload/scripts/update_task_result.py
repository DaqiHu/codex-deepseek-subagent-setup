#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import stat
import sys
import uuid


REQUIRED_HEADINGS = (
    "### Findings",
    "### Concerns",
    "### Alternatives",
    "### Open Questions",
)
RESULT_HEADING = "## Result"
# CommonMark ATX headings may be indented by up to three spaces; four or
# more spaces start an indented code block instead.
HEADING_PATTERN = re.compile(rb"^ {0,3}## Result[ \t]*(?:\r?\n|$)", re.MULTILINE)


def configure_standard_streams() -> None:
    """Keep the writer protocol UTF-8 regardless of the platform locale."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict")


def fail(message: str, code: int) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def validate_result(result: str) -> None:
    """Require every pinned heading exactly once, in pinned order."""
    lines = result.splitlines()
    if HEADING_PATTERN.search(result.encode("utf-8")) is not None:
        raise ValueError("The Result must not contain a standalone ## Result heading.")
    for heading in REQUIRED_HEADINGS:
        count = sum(1 for line in lines if line == heading)
        if count != 1:
            raise ValueError(
                "The Result must contain the required headings, each exactly once: "
                + ", ".join(REQUIRED_HEADINGS)
            )
    positions = [lines.index(heading) for heading in REQUIRED_HEADINGS]
    if positions != sorted(positions):
        raise ValueError(
            "The Result required headings must appear in the pinned order: "
            + ", ".join(REQUIRED_HEADINGS)
        )


def locate_result_heading(task_bytes: bytes) -> int:
    matches = list(HEADING_PATTERN.finditer(task_bytes))
    if not matches:
        raise ValueError("The task file is missing the '## Result' heading.")
    return matches[-1].start()


def detect_dominant_line_ending(task_bytes: bytes) -> bytes:
    """Pick the newline convention that dominates the given byte prefix."""
    crlf_count = task_bytes.count(b"\r\n")
    lf_count = task_bytes.count(b"\n") - crlf_count
    return b"\r\n" if crlf_count > lf_count else b"\n"


def write_bytes_atomically(path: Path, payload: bytes) -> None:
    mode = path.stat().st_mode
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        # Best-effort cleanup: a failed replace (e.g. a read-only destination
        # on Windows) must leave no temp artifact and must never mask the
        # primary error with a cleanup failure.
        try:
            os.chmod(temporary, mode | stat.S_IWRITE)
        except OSError:
            pass
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def write_result(task: Path, result: str) -> None:
    task_bytes = task.read_bytes()
    offset = locate_result_heading(task_bytes)
    line_ending = detect_dominant_line_ending(task_bytes[:offset])
    normalized = result.replace("\r\n", "\n").replace("\r", "\n")
    normalized = (normalized.rstrip() + "\n").replace("\n", line_ending.decode("ascii"))
    payload = task_bytes[:offset] + b"## Result" + line_ending + normalized.encode("utf-8")
    write_bytes_atomically(task, payload)


def main() -> None:
    configure_standard_streams()
    parser = argparse.ArgumentParser(
        description=(
            "Replace only the '## Result' section of a task file with a validated "
            "four-section Result read from stdin."
        )
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Absolute path to the task markdown file.",
    )
    arguments = parser.parse_args()
    task = Path(arguments.task).expanduser().resolve()
    try:
        result = sys.stdin.read()
    except UnicodeError as error:
        fail(f"The Result input was not valid UTF-8. ({error})", 10)
    try:
        validate_result(result)
    except ValueError as error:
        fail(str(error), 2)
    try:
        write_result(task, result)
    except ValueError as error:
        fail(str(error), 2)
    except OSError as error:
        fail(f"Could not write the task Result: {error}", 3)


if __name__ == "__main__":
    main()
