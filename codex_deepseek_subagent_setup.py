#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Recreate the Codex DeepSeek V4 Flash worker setup in the Codex home.

Cross-platform (macOS / Linux / Windows) idempotent installer that reproduces
the full v4_flash_worker configuration:

1. ``<codex-home>/agents/v4-flash-worker.toml`` — the custom agent (model
   ``deepseek-v4-flash``, provider ``deepseek``, sandbox ``danger-full-access``,
   provider block with base URL + bearer token).
2. ``<codex-home>/skills/use-v4-flash-worker/`` — ``SKILL.md`` (including the
   task-handoff integration section) and ``agents/openai.yaml``.
3. ``<codex-home>/hooks/codex-deepseek-subagent/`` — the platform handoff
   script (``plaintext_handoff.py``), copied from the existing install or
   downloaded from the upstream repository and verified against a pinned
   SHA-256 (Python is assumed on every platform, including Windows).
4. ``<codex-home>/hooks.json`` — the ``SubagentStart`` Hook (matcher
   ``^v4_flash_worker$``), merged without touching unrelated hooks and without
   writing any trust hash.
5. ``<codex-home>/config.toml`` — the ``[features.multi_agent_v2]`` block
   (``hide_spawn_agent_metadata = false``, ``tool_namespace = "agents"``).
6. ``<codex-home>/AGENTS.md`` — the routing and task-handoff blocks, replaced
   idempotently inside their start/end markers.

Credential resolution (interactive on a TTY, automatic otherwise):
1. Explicit interactive input — base URL and API key are prompted separately
   (the key is echoed while typing); pressing Enter on either field
   auto-resolves.
2. ``~/.kimi-code/config.toml`` (``[providers.opencode-go]``) — base URL and
   token written into the agent file as ``experimental_bearer_token``.
3. Fallback on every platform: official DeepSeek endpoint + ``env_key =
   "DEEPSEEK_API_KEY"`` (Python is assumed installed on Windows too; there is
   no PowerShell variant).
The key is never embedded in this script and never printed.

Backups: before any change is written, the managed files are snapshotted to
``~/.codex-backups/codex-deepseek-subagent/<timestamp>/`` — deliberately
outside the Codex home so that config switchers (cc-switch) that swap
``~/.codex`` never destroy the backup. Restore with ``--restore``.

Subcommands:
    (default)        install / sync idempotently
    --dry-run        preview what would change without writing anything
    --restore [ID]   restore from a backup (ID is a timestamp, or "latest")
    --manual         print this manual and exit
    -h, --help       print the short usage and exit

Usage:
    python3 codex_deepseek_subagent_setup.py [--dry-run] [--backup-dir PATH]
                                             [--skip-backup]
    python3 codex_deepseek_subagent_setup.py --restore [ID] [--backup-dir PATH]
"""

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
import tomllib
import urllib.request
from datetime import datetime, timezone

UPSTREAM_RAW = (
    "https://raw.githubusercontent.com/Utopia-V/codex-deepseek-subagent/main"
)
HANDOFF_FILENAME = "plaintext_handoff.py"
HANDOFF_SHA256 = "6ef11b57dfedba950ebd69f30edffc25480072d384968f1410c574db94dda634"
MANAGED_FILES = [
    "agents/v4-flash-worker.toml",
    "skills/use-v4-flash-worker/SKILL.md",
    "skills/use-v4-flash-worker/agents/openai.yaml",
    "hooks.json",
    "config.toml",
    "AGENTS.md",
]

AGENT_TOML_TEMPLATE = '''name = "v4_flash_worker"

description = "Fast text-only DeepSeek V4 Flash worker for bounded code, log, search, extraction, and high-volume reading tasks. Before spawning or continuing it, the parent should use $use-v4-flash-worker for the installed plaintext-Hook workflow. The parent decides whether to delegate and owns scope, context, effort, verification, continuation, and integration."

developer_instructions = """
Execute the assignment within the scope, permissions, and output contract supplied by the parent.
Treat the parent's choices about context, tools, verification depth, reporting cadence, and stopping condition as authoritative.
Do only the work needed for the assignment. Do not inspect unrelated workspace state, broaden the task, mutate files, or manage other agents unless the assignment explicitly requires it.
If essential input is missing or the configured provider cannot be used, report the blocker; never silently substitute another model, provider, application, or invocation path.
Treat a developer-context block delimited by BEGIN PARENT ASSIGNMENT and END PARENT ASSIGNMENT as the complete parent-supplied task contract. Do not continue unrelated root work or infer a task from surrounding history.
If no marked plaintext handoff is present, accept inherited context only when it contains one explicit assignment addressed to v4_flash_worker and clearly distinguishes root and child responsibilities. Otherwise report the missing input instead of guessing or spawning another agent.
Return in the requested form. If no form is specified, return the result with only decisive evidence and material caveats.
"""

model_provider = "deepseek"
model = "deepseek-v4-flash"
model_context_window = 1000000
# Customized: upstream default is read-only; this install intentionally runs
# the worker with full access.
sandbox_mode = "danger-full-access"

[model_providers.deepseek]
name = "DeepSeek"
base_url = "{base_url}"
wire_api = "responses"
{provider_lines}
'''

SKILL_MD = '''---
name: use-v4-flash-worker
description: Use the DeepSeek-backed v4_flash_worker through the installed one-shot plaintext SubagentStart Hook. Use whenever Codex considers spawning, continuing, or troubleshooting this worker; it governs task suitability, plaintext staging, fork_turns=none, idle callback, failure recovery, V1 fallback boundaries, and the DeepSeek data boundary.
---

# Use V4 Flash Worker

## Choose the worker

- Use it for bounded, preferably read-only text, code, log, search, extraction,
  enumeration, or high-volume reading work whose raw material is much larger
  than the useful conclusion.
- Keep tightly coupled reasoning, consequential decisions, verification, and
  final integration in the parent. Use a multimodal worker when the task needs
  image understanding.
- Do not send secrets, private source, personal data, or regulated material
  unless the user has authorized the external DeepSeek data boundary.

## Deliver one self-contained job

1. Build one complete assignment containing child identity, objective, scope,
   exclusions, available permissions, evidence or output contract, and stopping
   condition. Keep it in parent-owned execution state; do not publish it as
   user-visible commentary merely for transport.
2. Pipe the assignment through stdin to the installed handoff script in
   `stage` mode. Use the standard installed path below. If it is absent, inspect
   the effective `SubagentStart` Hook matching `^v4_flash_worker$` and use the
   same reviewed script path with its mode changed from `hook` to `stage`:
   - Windows: `python3 "<codex-home>\\hooks\\codex-deepseek-subagent\\plaintext_handoff.py" --mode stage`
   - macOS/Linux: `python3 "<codex-home>/hooks/codex-deepseek-subagent/plaintext_handoff.py" --mode stage`
3. Require a successful stage result naming `v4_flash_worker`. Do not echo the
   assignment, replace an active or malformed pending item, or stage a second
   Flash job before the first is consumed.
4. Immediately spawn the exact agent type `v4_flash_worker` with a unique task
   name and `fork_turns="none"`. The spawn message may point to the trusted
   one-shot Hook but must not contain the only copy of essential instructions.
   Let the parent choose ordinary reasoning effort; do not invent a token budget.
5. Use one task-sized native idle wait or callback. Do not short-poll, duplicate
   the child work, or invent another transport while it runs.
6. Verify the returned contribution in proportion to the parent claim, then
   integrate it in the parent context.

## Integrate with the task-handoff contract system

When the parent's task originates from the task-handoff skill
(`~/.agents/skills/task-handoff`, which Codex loads from the `~/.agents` skill
path), the task contract lives in a `.kanpd/docs/tasks/task-*.md` file with a
pinned four-section `## Result`. Keep that system's discipline and use the
Hook only as the transport:

- **Assignment construction.** Build the staged assignment from the task
  file's contract — Objective, Context, Files to Read, Instructions,
  Acceptance Criteria, Constraints — wrapped with the child identity,
  boundary, output contract, and stopping condition. Include the task file's
  absolute path as an audit anchor. Do not send only the path: the child must
  receive the full contract through the Hook, not a pointer it must resolve.
- **Result return.** Ask for the four-section result (Findings / Concerns /
  Alternatives / Open Questions) matching the task file's `## Result` shape.
  The child may write `## Result` directly into the task file when the
  assignment grants the path (frontmatter stays off-limits); otherwise return
  the four sections as text and the parent transcribes them (the task-handoff
  fallback for agents without write access).
- **Single source of truth.** The staged assignment and the task file must not
  drift. If the contract changes after staging, stage a new assignment and
  spawn a fresh child instead of reusing the stale one.
- **No lifecycle duplication.** Tier classification, quality gates, archiving,
  and disk audit stay with the task-handoff skill in the parent; the Hook
  delivers the contract, it does not manage it.

## Fail and continue safely

- Treat a missing Hook assignment, failed stage, unreadable child task, or
  absent callback as a transport failure. Do not silently substitute another
  provider, model, app, direct API call, CLI process, or inherited root history.
- Current V2 `send_message` and `followup_task` payloads can cross the same
  encryption boundary. When essential task information changes, stage a new
  self-contained job and start a new child.
- An unconsumed item expires after its TTL. A later stage may recover only a
  structurally valid expired item; never delete or overwrite unknown state.
- Multi-agent V1 is an explicit top-level session compatibility choice, not a
  per-spawn switch or silent fallback.
- The staged assignment briefly exists as plaintext in local user state before
  it is sent to DeepSeek. The Hook is a transport compatibility layer, not a
  confidential channel.
'''

OPENAI_YAML = '''interface:
  display_name: "Use V4 Flash Worker"
  short_description: "Reliable plaintext handoff to DeepSeek Flash"
  default_prompt: "Use $use-v4-flash-worker to delegate this bounded task through the installed plaintext Hook."
'''

AGENTS_MD = '''<!-- codex-deepseek-subagent:start -->
- Routing: prefer `v4_flash_worker` by default for bounded text, code, log, search, extraction, enumeration, or high-volume reading work. The parent decides and owns scope, verification, and integration; reserve built-in OpenAI subagents for multimodal or tightly coupled OpenAI work.
- Dispatch: before spawning, continuing, or troubleshooting `v4_flash_worker`, use `$use-v4-flash-worker` and follow its plaintext-Hook workflow. Do not bypass it with V2 message-only delivery or inherited root turns.
<!-- codex-deepseek-subagent:end -->

<!-- task-handoff:start -->
- Follow the task-handoff skill for multi-step work: 30-second Quick Assessment, tier classification (XS-XL), contract files under `.kanpd/docs/tasks/`, dispatch by absolute path, audit `## Result` from disk. Skill: `~/.agents/skills/task-handoff` (loaded from the `~/.agents` skill path).
- Contracts dispatched to `v4_flash_worker`: stage the full contract as the assignment and return the four-section Result (see `$use-v4-flash-worker`, "Integrate with the task-handoff contract system").
<!-- task-handoff:end -->
'''

FEATURES_BLOCK = (
    "\n[features.multi_agent_v2]\n"
    'hide_spawn_agent_metadata = false\n'
    'tool_namespace = "agents"\n'
)

MANUAL = """\
MANUAL — codex_deepseek_subagent_setup.py
=========================================

What it manages (relative to the Codex home, CODEX_HOME or ~/.codex):
  1. agents/v4-flash-worker.toml          custom agent: deepseek-v4-flash,
                                          provider deepseek, sandbox
                                          danger-full-access, base URL +
                                          bearer token from ~/.kimi-code
                                          config (opencode-go)
  2. skills/use-v4-flash-worker/          SKILL.md (with the task-handoff
                                          integration section) + openai.yaml
  3. hooks/codex-deepseek-subagent/       platform handoff script, verified
                                          against a pinned SHA-256
  4. hooks.json                           SubagentStart Hook (matcher
                                          ^v4_flash_worker$), merged without
                                          touching unrelated hooks or trust
                                          hashes
  5. config.toml                          [features.multi_agent_v2] block,
                                          text-level idempotent injection
  6. AGENTS.md                            routing + task-handoff blocks,
                                          replaced inside their markers only

Credential resolution, in order:
  1. Interactive input (only on a TTY; press Enter to skip each field):
     base URL and API key are prompted separately, so either can be
     overridden independently.
  2. ~/.kimi-code/config.toml [providers.opencode-go] (base_url + api_key)
     -> written into the agent file as experimental_bearer_token
  3. Fallback: official https://api.deepseek.com + env_key
     DEEPSEEK_API_KEY (set it in the environment of the Codex process;
     on Windows: setx DEEPSEEK_API_KEY "sk-..." )
The key is never printed and never committed to this script.

Backups (cc-switch safe):
  - Created automatically before the first write of a run, stored under
    ~/.codex-backups/codex-deepseek-subagent/<timestamp>/  — deliberately
    OUTSIDE the Codex home so that switching ~/.codex (cc-switch) cannot
    destroy them. Override the location with --backup-dir.
  - Each backup holds a manifest.json plus copies of every managed file.
  - Restore with:  python3 codex_deepseek_subagent_setup.py --restore [ID]
    where ID is a backup timestamp or "latest" (default). The restore is a
    full-file snapshot restore; if config.toml / AGENTS.md differ from the
    backup (e.g. cc-switch changed them), the script prints the differences
    and still restores the snapshot — review before confirming.
  - --dry-run never backs up and never writes.

Windows notes:
  - Python 3 is assumed installed; the same plaintext_handoff.py is used on
    every platform (no PowerShell variant).
  - Run with:  python3 codex_deepseek_subagent_setup.py
  - Backups land under %USERPROFILE%\\.codex-backups\\codex-deepseek-subagent\\.

After a successful run:
  1. Fully restart the ChatGPT app / Codex process (config is loaded at
     startup), 2. open /hooks and trust the SubagentStart definition (the
     script never writes a trust hash), 3. start a NEW task, 4. optionally
     run the quick-smoke-test flow for a real end-to-end check.

Upstream: https://github.com/Utopia-V/codex-deepseek-subagent
"""


def section(title):
    print(f"\n=== {title} ===")


def status(mark, message):
    print(f"  [{mark}] {message}")


def write_utf8(path, content):
    """Write with LF line endings on every platform (stable idempotence)."""
    path.write_text(content, encoding="utf-8", newline="\n")


def read_utf8(path):
    return path.read_text(encoding="utf-8")


def sha256_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_windows():
    return os.name == "nt"


def codex_home_from_env():
    override = os.environ.get("CODEX_HOME")
    if override:
        return pathlib.Path(override).expanduser()
    return pathlib.Path.home() / ".codex"


def load_opencode_go_credentials():
    """Return (base_url, api_key) from ~/.kimi-code/config.toml, or (None, None)."""
    kimi_config = pathlib.Path.home() / ".kimi-code" / "config.toml"
    if not kimi_config.exists():
        return None, None
    try:
        data = tomllib.loads(read_utf8(kimi_config))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None, None
    provider = data.get("providers", {}).get("opencode-go", {})
    api_key = provider.get("api_key")
    base_url = provider.get("base_url")
    if api_key and base_url:
        return base_url, api_key
    return None, None


def resolve_credentials():
    """Resolve (base_url, provider_lines, source_label) for the agent TOML.

    Priority: explicit interactive input > ~/.kimi-code opencode-go > fallback.
    Interactive prompts only appear on a TTY; piped/non-interactive runs skip
    straight to the automatic resolution. An empty input means "auto".
    """
    kimi_base, kimi_key = load_opencode_go_credentials()
    user_base = None
    user_key = None
    if sys.stdin.isatty():
        print("Credential input (press Enter to auto-resolve):")
        hint = kimi_base or "https://api.deepseek.com"
        user_base = input(f"  base URL [{hint}]: ").strip() or None
        print("  API key (visible while typing; Enter to auto-resolve): ", end="", flush=True)
        user_key = input().strip() or None
    base_url = user_base or kimi_base or "https://api.deepseek.com"
    if user_key or kimi_key:
        api_key = user_key or kimi_key
        provider_lines = f'experimental_bearer_token = "{api_key}"'
        source = "user input" if user_key else "~/.kimi-code [providers.opencode-go]"
    else:
        provider_lines = 'env_key = "DEEPSEEK_API_KEY"'
        source = "env var DEEPSEEK_API_KEY (official endpoint)"
    return base_url, provider_lines, source


def ensure_agent_toml(codex_home, base_url, provider_lines, dry_run):
    target = codex_home / "agents" / "v4-flash-worker.toml"
    content = AGENT_TOML_TEMPLATE.format(
        base_url=base_url, provider_lines=provider_lines
    )
    existing = read_utf8(target) if target.exists() else None
    if existing == content:
        status("OK", "agents/v4-flash-worker.toml unchanged")
        return False
    if dry_run:
        status("DRY", "agents/v4-flash-worker.toml would be written")
        return True
    target.parent.mkdir(parents=True, exist_ok=True)
    write_utf8(target, content)
    if not is_windows():
        target.chmod(0o600)
    status("WROTE", "agents/v4-flash-worker.toml")
    return True


def ensure_skill(codex_home, dry_run):
    changed = False
    skill_dir = codex_home / "skills" / "use-v4-flash-worker"
    for rel, content in (
        ("SKILL.md", SKILL_MD),
        ("agents/openai.yaml", OPENAI_YAML),
    ):
        target = skill_dir / rel
        existing = read_utf8(target) if target.exists() else None
        if existing == content:
            status("OK", f"skills/use-v4-flash-worker/{rel} unchanged")
            continue
        if dry_run:
            status("DRY", f"skills/use-v4-flash-worker/{rel} would be written")
            changed = True
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        write_utf8(target, content)
        status("WROTE", f"skills/use-v4-flash-worker/{rel}")
        changed = True
    return changed


def ensure_handoff_script(codex_home, dry_run):
    """Copy the local handoff script if present; otherwise fetch from upstream."""
    filename = HANDOFF_FILENAME
    pinned = HANDOFF_SHA256
    target = codex_home / "hooks" / "codex-deepseek-subagent" / filename
    if target.exists():
        actual = sha256_of(target)
        if actual == pinned:
            status("OK", f"hooks/codex-deepseek-subagent/{filename} unchanged")
            return
        status(
            "SKIP",
            f"hooks/codex-deepseek-subagent/{filename} differs from upstream "
            f"SHA-256 ({actual[:12]}...); not overwriting a locally modified file",
        )
        return
    if dry_run:
        status("DRY", f"hooks/codex-deepseek-subagent/{filename} would be downloaded")
        return
    url = f"{UPSTREAM_RAW}/hooks/{filename}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = response.read()
    except OSError as error:
        status(
            "FAIL",
            f"download failed ({error}); install manually from {url}",
        )
        return
    actual = hashlib.sha256(payload).hexdigest()
    if actual != pinned:
        status(
            "FAIL",
            f"downloaded {filename} SHA-256 mismatch ({actual[:12]}...); "
            "refusing to install",
        )
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    status("WROTE", f"hooks/codex-deepseek-subagent/{filename} downloaded (SHA-256 verified)")


def handoff_script_path(codex_home):
    return codex_home / "hooks" / "codex-deepseek-subagent" / HANDOFF_FILENAME


def build_hooks_template(handoff_script):
    command = f'python3 "{handoff_script}" --mode hook'
    return {
        "description": "One-shot plaintext task handoff for the DeepSeek-backed v4_flash_worker.",
        "hooks": {
            "SubagentStart": [
                {
                    "matcher": "^v4_flash_worker$",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command,
                            "timeout": 10,
                            "statusMessage": "Delivering the staged Flash assignment",
                            "additionalContextLimit": 0,
                        }
                    ],
                }
            ]
        },
    }


def ensure_hooks_json(codex_home, handoff_script, dry_run):
    """Merge the SubagentStart hook, preserving unrelated hooks."""
    target = codex_home / "hooks.json"
    template = build_hooks_template(handoff_script)
    if not target.exists():
        if dry_run:
            status("DRY", "hooks.json would be created")
            return True
        write_utf8(target, json.dumps(template, indent=2) + "\n")
        status("WROTE", "hooks.json created")
        return True
    data = json.loads(read_utf8(target))
    groups = data.setdefault("hooks", {}).setdefault("SubagentStart", [])
    for group in groups:
        if group.get("matcher") == "^v4_flash_worker$":
            group["hooks"] = template["hooks"]["SubagentStart"][0]["hooks"]
            serialized = json.dumps(data, indent=2) + "\n"
            if read_utf8(target) == serialized:
                status("OK", "hooks.json unchanged")
                return False
            if dry_run:
                status("DRY", "hooks.json would be updated")
                return True
            write_utf8(target, serialized)
            status("WROTE", "hooks.json updated existing v4_flash_worker hook group")
            return True
    data["hooks"]["SubagentStart"].append(template["hooks"]["SubagentStart"][0])
    if dry_run:
        status("DRY", "hooks.json would gain the v4_flash_worker hook group")
        return True
    write_utf8(target, json.dumps(data, indent=2) + "\n")
    status("WROTE", "hooks.json merged v4_flash_worker hook group")
    return True


def ensure_features_multi_agent_v2(config_path, dry_run):
    """Text-level idempotent injection of the [features.multi_agent_v2] block."""
    if not config_path.exists():
        status("SKIP", f"config.toml missing ({config_path})")
        return False
    text = read_utf8(config_path)
    if "[features.multi_agent_v2]" in text:
        had_metadata = "hide_spawn_agent_metadata = false" in text
        had_namespace = 'tool_namespace = "agents"' in text
        if had_metadata and had_namespace:
            status("OK", "config.toml [features.multi_agent_v2] unchanged")
            return False
        updated = text
        if not had_metadata:
            updated = re.sub(
                r"(?m)^hide_spawn_agent_metadata = .*$",
                "hide_spawn_agent_metadata = false",
                updated,
            )
        if not had_namespace:
            updated = re.sub(
                r'(?m)^tool_namespace = ".*"$',
                'tool_namespace = "agents"',
                updated,
            )
        if dry_run:
            status("DRY", "config.toml [features.multi_agent_v2] would be updated")
            return True
        write_utf8(config_path, updated)
        status("WROTE", "config.toml [features.multi_agent_v2] updated")
        return True
    if dry_run:
        status("DRY", "config.toml would gain the [features.multi_agent_v2] block")
        return True
    with config_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(FEATURES_BLOCK)
    status("WROTE", "config.toml appended [features.multi_agent_v2] block")
    return True


def ensure_agents_md(codex_home, dry_run):
    """Replace the two marked blocks idempotently, preserving unrelated lines."""
    target = codex_home / "AGENTS.md"
    if not target.exists():
        if dry_run:
            status("DRY", "AGENTS.md would be created")
            return True
        write_utf8(target, AGENTS_MD)
        status("WROTE", "AGENTS.md created")
        return True
    text = read_utf8(target)
    first_block = re.search(
        r"<!-- codex-deepseek-subagent:start -->.*?<!-- codex-deepseek-subagent:end -->",
        text,
        flags=re.S,
    )
    second_block = re.search(
        r"<!-- task-handoff:start -->.*?<!-- task-handoff:end -->",
        text,
        flags=re.S,
    )
    split_point = AGENTS_MD.index("\n\n<!-- task-handoff:start -->")
    first_half = AGENTS_MD[:split_point]
    second_half = AGENTS_MD[split_point + 2:]
    if first_block and second_block:
        updated = text
        updated = updated.replace(first_block.group(0), first_half.strip())
        updated = updated.replace(second_block.group(0), second_half.strip())
        updated = re.sub(r"\n{3,}", "\n\n", updated).strip() + "\n"
    elif first_block or second_block:
        updated = AGENTS_MD
    else:
        updated = text.rstrip() + "\n\n" + AGENTS_MD
    if read_utf8(target) == updated:
        status("OK", "AGENTS.md unchanged")
        return False
    if dry_run:
        status("DRY", "AGENTS.md would be updated")
        return True
    write_utf8(target, updated)
    status("WROTE", "AGENTS.md")
    return True


def validate(codex_home):
    checks = (
        ("agents/v4-flash-worker.toml", tomllib.loads),
        ("config.toml", tomllib.loads),
        ("hooks.json", json.loads),
    )
    all_ok = True
    for rel, parser in checks:
        path = codex_home / rel
        if not path.exists():
            status("SKIP", f"validation skipped: {rel} does not exist")
            continue
        parser(read_utf8(path))
        all_ok = all_ok and True
    if all_ok:
        status("OK", "validation: TOML (agent, config) and JSON (hooks) all parse")


def default_backup_root():
    return pathlib.Path.home() / ".codex-backups" / "codex-deepseek-subagent"


def create_backup(codex_home, backup_root):
    """Snapshot all managed files into a timestamped directory; returns path."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup_dir = backup_root / stamp
    files_dir = backup_dir / "files"
    manifest = {
        "created_at": stamp,
        "platform": os.name,
        "codex_home": str(codex_home),
        "files": {},
    }
    for rel in MANAGED_FILES:
        source = codex_home / rel
        if not source.exists():
            continue
        destination = files_dir / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        manifest["files"][rel] = sha256_of(source)
    write_utf8(backup_dir / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    return backup_dir


def list_backups(backup_root):
    if not backup_root.exists():
        return []
    return sorted(
        (entry for entry in backup_root.iterdir() if entry.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )


def restore_backup(backup_dir, codex_home):
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        status("FAIL", f"no manifest.json in {backup_dir}")
        return False
    manifest = json.loads(read_utf8(manifest_path))
    section(f"Restoring from backup {backup_dir.name} "
            f"(created {manifest.get('created_at')}, "
            f"platform {manifest.get('platform')})")
    restored = 0
    for rel, expected_sha in manifest.get("files", {}).items():
        source = backup_dir / "files" / rel
        target = codex_home / rel
        if not source.exists():
            status("SKIP", f"{rel} missing in backup")
            continue
        current_sha = sha256_of(target) if target.exists() else None
        if current_sha != expected_sha:
            status(
                "WARN",
                f"{rel} differs from the backup snapshot; restoring over it",
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        status("RESTORED", rel)
        restored += 1
    section("Post-restore validation")
    validate(codex_home)
    status(
        "NOTE",
        "restore is a full-file snapshot; re-run the installer afterwards to "
        "resync the managed content if needed",
    )
    return restored > 0


def cmd_restore(args):
    backup_root = pathlib.Path(args.backup_dir).expanduser()
    backups = list_backups(backup_root)
    if not backups:
        status("FAIL", f"no backups found under {backup_root}")
        return 1
    if args.restore and args.restore != "latest":
        matches = [b for b in backups if b.name == args.restore]
        if not matches:
            status("FAIL", f"backup {args.restore} not found; available:")
            for backup in backups:
                status("BACKUP", backup.name)
            return 1
        chosen = matches[0]
    else:
        chosen = backups[0]
        status("INFO", f"no ID given; using latest backup {chosen.name}")
    restore_backup(chosen, codex_home_from_env())
    return 0


def cmd_install(args):
    codex_home = codex_home_from_env()
    section(f"Codex home: {codex_home}  (platform: "
            f"{'windows' if is_windows() else 'posix'})")

    resolved_base, provider_lines, source = resolve_credentials()
    status("INFO", f"credential source: {source}")
    if "env var" in source:
        status(
            "WARN",
            "no API key provided; the worker will read DEEPSEEK_API_KEY from the "
            "Codex process environment at runtime",
        )

    changed = 0
    changed += ensure_agent_toml(codex_home, resolved_base, provider_lines, args.dry_run)
    changed += ensure_skill(codex_home, args.dry_run)
    ensure_handoff_script(codex_home, args.dry_run)
    changed += ensure_hooks_json(codex_home, handoff_script_path(codex_home), args.dry_run)
    changed += ensure_features_multi_agent_v2(codex_home / "config.toml", args.dry_run)
    changed += ensure_agents_md(codex_home, args.dry_run)

    if not args.dry_run:
        section("Validation")
        validate(codex_home)

    section("Summary")
    status("CHANGED" if changed else "OK",
           f"{changed} file(s) changed; run with --dry-run to preview")
    if changed and not args.dry_run and not args.skip_backup:
        backup_root = pathlib.Path(args.backup_dir).expanduser()
        backup_dir = create_backup(codex_home, backup_root)
        status(
            "BACKUP",
            f"pre-change snapshot saved to {backup_dir} "
            f"(outside the Codex home; cc-switch safe)",
        )
    elif changed and not args.dry_run:
        status("SKIP", "backup skipped (--skip-backup)")
    status(
        "NEXT",
        "restart the ChatGPT app / Codex, trust the SubagentStart Hook in "
        "/hooks, then start a NEW task",
    )
    return 0


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        prog="codex-deepseek-subagent-setup",
        description=(
            "Cross-platform idempotent installer for the Codex DeepSeek "
            "V4 Flash worker (agent, skill, Hook, config, AGENTS.md). "
            "Backs up before changing; restore with --restore. "
            "See --manual for the full manual."
        ),
        epilog=(
            "Examples:\n"
            "  python3 codex_deepseek_subagent_setup.py                 # install/sync\n"
            "  python3 codex_deepseek_subagent_setup.py --dry-run       # preview only\n"
            "  python3 codex_deepseek_subagent_setup.py --restore       # restore latest\n"
            "  python3 codex_deepseek_subagent_setup.py --restore 20260807-183000\n"
            "  python3 codex_deepseek_subagent_setup.py --manual        # full manual"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="preview what would change without writing or backing up anything",
    )
    parser.add_argument(
        "--backup-dir", default=str(default_backup_root()),
        help=f"backup directory (default: {default_backup_root()})",
    )
    parser.add_argument(
        "--skip-backup", action="store_true",
        help="do not create a pre-change backup snapshot",
    )
    parser.add_argument(
        "--restore", nargs="?", const="latest", metavar="ID",
        help="restore from a backup ID (timestamp) or 'latest' (default)",
    )
    parser.add_argument(
        "--manual", action="store_true",
        help="print the full manual and exit",
    )
    args = parser.parse_args()

    if args.manual:
        print(MANUAL)
        return 0
    if args.restore:
        return cmd_restore(args)
    return cmd_install(args)


if __name__ == "__main__":
    sys.exit(main())
