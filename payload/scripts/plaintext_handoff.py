#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
import uuid


AGENT_TYPE = "v4_flash_worker"
THREAD_ID_ENV = "CODEX_THREAD_ID"
ROUTING_KEY_HEX_LENGTH = 24
# Strict hook-side output cap: the installed SubagentStart Hook keeps
# additionalContextLimit at 0 (Codex docs allow 0 only when the hook enforces a
# strict output cap), so stage() refuses assignments above this bound before
# publishing any pending state. 32 KiB bounds the additional context well below
# the model window while leaving room for full task contracts.
MAX_ASSIGNMENT_BYTES_DEFAULT = 32 * 1024


class HandoffError(Exception):
    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


def configure_standard_streams() -> None:
    """Make the hook protocol UTF-8 even when Python inherited cp936 on Windows.

    Strict errors are deliberate: a caller that pipes non-UTF-8 bytes must fail
    loudly at the read boundary (stage: exit 10; hook: exit 4) instead of
    silently producing a surrogate-mangled assignment or a partial artifact.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict")


def state_root(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    override = os.environ.get("CODEX_DEEPSEEK_HANDOFF_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "Codex" / "plaintext-subagent-handoff"
    xdg_state = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg_state).expanduser() if xdg_state else Path.home() / ".local" / "state"
    return base / "codex" / "plaintext-subagent-handoff"


def fail(message: str, code: int) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def publish_pending_atomically(pending: Path, envelope: dict[str, Any]) -> None:
    """Publish only a complete UTF-8 envelope without replacing another stage."""
    payload = json.dumps(
        envelope,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    temporary = pending.with_name(f".{pending.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, pending)
    finally:
        temporary.unlink(missing_ok=True)


def read_pending(pending: Path) -> dict[str, Any]:
    try:
        with pending.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise HandoffError(
            f"The existing Flash handoff is unreadable ({error}). Move it aside for inspection; "
            "the script will not overwrite unknown state.",
            9,
        ) from error
    if not isinstance(value, dict):
        raise HandoffError("The existing Flash handoff is not a JSON object.", 9)
    return value


def parse_expiry(envelope: dict[str, Any], *, code: int) -> datetime.datetime:
    expires_at = envelope.get("expires_at")
    if envelope.get("schema") != 1 or envelope.get("agent_type") != AGENT_TYPE or not expires_at:
        raise HandoffError("The Flash handoff has an invalid schema, agent type, or expiry.", code)
    try:
        return datetime.datetime.fromisoformat(str(expires_at))
    except ValueError as error:
        raise HandoffError("The Flash handoff expiry is not valid ISO 8601.", code) from error


def require_session_id(value: object, *, source: str) -> str:
    """Return a non-empty session id without ever logging its value."""
    session_id = str(value or "").strip()
    if not session_id:
        fail(
            f"Missing Codex session identity from {source}. Stage requires {THREAD_ID_ENV}; "
            "SubagentStart hook input requires session_id. Refusing an unbound handoff.",
            12,
        )
    return session_id


def routing_key(session_id: str) -> str:
    """Hash a session id into a path-safe, non-reversible routing key."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:ROUTING_KEY_HEX_LENGTH]


def pending_path(root: Path, session_id: str) -> Path:
    return root / f"{AGENT_TYPE}.{routing_key(session_id)}.pending.json"


def stage(
    root: Path,
    ttl_seconds: int,
    max_assignment_bytes: int,
    session_id: str | None = None,
) -> None:
    try:
        assignment = sys.stdin.read()
    except UnicodeError as error:
        fail(
            "Staging input was not valid UTF-8. Make the pipe UTF-8 (PowerShell: "
            "$OutputEncoding / $env:PYTHONUTF8) or fix the assignment encoding. "
            f"({error})",
            10,
        )
    if not assignment.strip():
        fail("Refusing to stage an empty Flash assignment.", 2)
    assignment_bytes = len(assignment.encode("utf-8"))
    if assignment_bytes > max_assignment_bytes:
        fail(
            f"Refusing to stage a {assignment_bytes}-byte Flash assignment; the strict hook-side "
            f"cap is {max_assignment_bytes} bytes. Reduce the assignment or split it into a fresh "
            "spawn, then restage.",
            11,
        )

    bound_session_id = require_session_id(
        session_id if session_id is not None else os.environ.get(THREAD_ID_ENV),
        source=THREAD_ID_ENV,
    )
    route = routing_key(bound_session_id)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    pending = pending_path(root, bound_session_id)
    now = datetime.datetime.now(datetime.timezone.utc)
    if pending.exists():
        try:
            existing = read_pending(pending)
            expires_at = parse_expiry(existing, code=9)
        except FileNotFoundError:
            existing = None
        except HandoffError as error:
            fail(str(error), error.code)
        if existing is not None:
            if expires_at > now:
                fail(
                    "A v4_flash_worker handoff is already pending. Let it be consumed or expire before staging another.",
                    3,
                )
            pending.unlink(missing_ok=True)

    envelope = {
        "schema": 1,
        "handoff_id": str(uuid.uuid4()),
        "agent_type": AGENT_TYPE,
        "routing_key": route,
        "created_at": now.isoformat(),
        "expires_at": (now + datetime.timedelta(seconds=ttl_seconds)).isoformat(),
        "assignment": assignment,
    }
    # A FileExistsError is normally a concurrent stage winning the race, but
    # the winner's pending may have been consumed by the hook before this
    # handler ran (observed as a transient "already pending" with no file).
    # Republish exactly once in that case; a real pending is never overwritten.
    for attempt in (0, 1):
        try:
            publish_pending_atomically(pending, envelope)
            break
        except FileExistsError:
            if attempt == 0 and not pending.exists():
                continue
            fail(
                "A v4_flash_worker handoff is already pending. Consume or remove it before staging another.",
                3,
            )

    json.dump(
        {
            "staged": True,
            "handoff_id": envelope["handoff_id"],
            "agent_type": AGENT_TYPE,
            "routing_key": route,
            "expires_at": envelope["expires_at"],
            "pending_path": str(pending),
        },
        sys.stdout,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    sys.stdout.flush()


def failed_claim_path(claimed: Path) -> Path:
    return claimed.with_name(claimed.name.replace(".claimed.", ".failed.", 1))


def run_hook(root: Path) -> None:
    try:
        hook_input = json.load(sys.stdin)
    except (UnicodeError, json.JSONDecodeError) as error:
        fail(f"SubagentStart hook input was invalid UTF-8 JSON: {error}", 4)
    if hook_input.get("hook_event_name") != "SubagentStart" or hook_input.get("agent_type") != AGENT_TYPE:
        return

    bound_session_id = require_session_id(
        hook_input.get("session_id"),
        source="SubagentStart hook input session_id",
    )
    route = routing_key(bound_session_id)
    pending = pending_path(root, bound_session_id)
    if not pending.exists():
        return
    agent_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(hook_input.get("agent_id") or uuid.uuid4().hex))
    claimed = root / f"{AGENT_TYPE}.{route}.claimed.{agent_id}.json"
    try:
        pending.rename(claimed)
    except FileNotFoundError:
        return

    try:
        envelope = read_pending(claimed)
        expires_at = parse_expiry(envelope, code=5)
        if envelope.get("routing_key") != route:
            raise HandoffError("The claimed Flash handoff routing key does not match this session.", 12)
        if expires_at <= datetime.datetime.now(datetime.timezone.utc):
            raise HandoffError("The pending Flash handoff expired before the child started.", 6)
        assignment = str(envelope.get("assignment") or "")
        if not assignment.strip():
            raise HandoffError("The pending Flash handoff contains no assignment.", 7)

        additional_context = (
            "You are the spawned v4_flash_worker child, not the root agent. The parent supplied the complete task below "
            "through a one-time plaintext handoff because provider-internal collaboration ciphertext is not a reliable "
            "cross-provider task carrier. Treat this as the task contract. Do not continue the parent's unrelated work "
            "and do not report the assignment missing merely because the encrypted collaboration payload is unreadable.\n\n"
            f"BEGIN PARENT ASSIGNMENT\n{assignment}\nEND PARENT ASSIGNMENT"
        )
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SubagentStart",
                    "additionalContext": additional_context,
                }
            },
            sys.stdout,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        sys.stdout.flush()
    except (HandoffError, OSError, UnicodeError, json.JSONDecodeError) as error:
        preserved = failed_claim_path(claimed)
        if claimed.exists():
            claimed.replace(preserved)
        code = error.code if isinstance(error, HandoffError) else 5
        fail(f"{error} Preserved the claimed handoff at {preserved}.", code)
    else:
        claimed.unlink(missing_ok=True)


def main() -> None:
    configure_standard_streams()
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("stage", "hook"))
    parser.add_argument("--ttl-seconds", type=int, default=300)
    parser.add_argument(
        "--max-assignment-bytes",
        type=int,
        default=MAX_ASSIGNMENT_BYTES_DEFAULT,
    )
    parser.add_argument("--state-directory")
    parser.add_argument(
        "--session-id",
        help=f"Explicit stage routing id; defaults to {THREAD_ID_ENV}. Not valid in hook mode.",
    )
    arguments = parser.parse_args()
    if not 1 <= arguments.ttl_seconds <= 3600:
        fail("--ttl-seconds must be between 1 and 3600.", 8)
    if not 1 <= arguments.max_assignment_bytes <= 1024 * 1024:
        fail("--max-assignment-bytes must be between 1 and 1048576.", 8)
    root = state_root(arguments.state_directory)
    if arguments.mode == "stage":
        stage(root, arguments.ttl_seconds, arguments.max_assignment_bytes, arguments.session_id)
        return
    if arguments.session_id is not None:
        fail("--session-id is only valid in stage mode; hook mode uses trusted hook input.", 8)
    run_hook(root)


if __name__ == "__main__":
    main()
