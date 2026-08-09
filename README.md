# codex-deepseek-subagent-setup

Authoritative cross-platform installer and lifecycle manager for the Codex
**v4_flash_worker**: a custom subagent that runs on `deepseek-v4-flash` while
the main agent keeps its own model, provider, and login untouched. One
self-contained Python script (PEP 723) installs the current Codex-only Hook,
skill, apply_patch/session-isolation helpers, AGENTS routing block, and Windows
UTF-8 environment, and then manages them safely with backup / restore /
remove.

The payload is byte-identical to the version-controlled authoritative skill
tree and is checked into this repository under `payload/` (plus a byte-exact
embedded copy so the one-shot raw-script path stays self-contained).

## What it manages

| File (relative to the Codex home, `CODEX_HOME` or `~/.codex`) | Content |
|---|---|
| `agents/v4-flash-worker.toml` | custom agent: `deepseek-v4-flash`, provider `deepseek`, `danger-full-access` sandbox, credential block |
| `skills/use-v4-flash-worker/` | `SKILL.md`, `agents/openai.yaml`, `agents/codex_AGENTS_block.md`, `scripts/plaintext_handoff.py`, `scripts/update_task_result.py`, `scripts/apply_patch.py`, `scripts/install.py` |
| `hooks/codex-deepseek-subagent/plaintext_handoff.py` | the session-scoped plaintext handoff Hook script |
| `hooks.json` | `SubagentStart` Hook (`^v4_flash_worker$`, timeout 60, `additionalContextLimit 0`, Windows `commandWindows` with `-X utf8`), merged; no trust hash is written |
| `config.toml` | `[shell_environment_policy.set]` with `PYTHONUTF8 = "1"` and `PYTHONIOENCODING = "utf-8"` so the Windows Hook runs as UTF-8 |
| `AGENTS.md` | the `codex-v4-flash-worker-agents` block (legacy `codex-deepseek-subagent` markers are migrated to exactly one new marker) |

Installer-owned hashes and state are tracked under
`<codex-home>/.codex-deepseek-subagent-setup/state.json`. The installer never
reads or writes the user agents configuration directory (`~/.agents`).

## Quick start

Requires Python 3.11+ (and optionally [uv](https://docs.astral.sh/uv/)).

```bash
# one-shot, no clone (uv) - the payload is embedded in the raw script:
uv run --refresh https://raw.githubusercontent.com/DaqiHu/codex-deepseek-subagent-setup/main/codex_deepseek_subagent_setup.py

# or run once from git, nothing installed (uv):
uvx --from git+https://github.com/DaqiHu/codex-deepseek-subagent-setup codex-deepseek-subagent-setup --dry-run

# or install as a persistent tool (uv):
uv tool install git+https://github.com/DaqiHu/codex-deepseek-subagent-setup
codex-deepseek-subagent-setup --status

# or clone and run:
git clone https://github.com/DaqiHu/codex-deepseek-subagent-setup
cd codex-deepseek-subagent-setup
python3 codex_deepseek_subagent_setup.py
```

The same commands work on Windows (PowerShell), macOS, and Linux. On a new
machine run the default install (or `--add` for a create-missing-only pass).

## Credentials

The installer prompts for base URL and API key on a TTY (press Enter to
auto-resolve). Resolution order:

1. explicit interactive input
2. an existing bearer token already installed in the agent file is preserved
   (a noninteractive `--update` never silently replaces it)
3. `~/.kimi-code/config.toml` → `[providers.opencode-go]` (base URL + token)
4. fallback: official `https://api.deepseek.com` + `DEEPSEEK_API_KEY` env var

The key is never embedded in the repository and never printed.

## Lifecycle actions

Actions are mutually exclusive; the default (no action flag) is an
idempotent install/upsert for backward compatibility.

| Command | Behavior |
|---|---|
| `(default)` | install/upsert: create missing artifacts and refresh owned content idempotently |
| `--add` | create only missing artifacts; never overwrite existing content (use `--update` to refresh) |
| `--update` | refresh owned content to the payload; preserves an existing credential token |
| `--backup` | create a backup snapshot now |
| `--list-backups` | list backup IDs |
| `--status` | report per-file install/ownership state (`--json` for machine output) |
| `--restore [ID]` | restore from a backup ID or `latest` (default) |
| `--remove` | remove only installer-owned content |

Shared flags: `--yes` (confirm destructive actions), `--force` (override
ownership checks), `--json` (JSON result on stdout), `--dry-run` (preview only),
`--backup-dir PATH`, `--skip-backup`, `--codex-home PATH`,
`--python-executable PATH`, `--manual`.

Examples:

```bash
python3 codex_deepseek_subagent_setup.py --add
python3 codex_deepseek_subagent_setup.py --update
python3 codex_deepseek_subagent_setup.py --status --json
python3 codex_deepseek_subagent_setup.py --backup
python3 codex_deepseek_subagent_setup.py --list-backups
python3 codex_deepseek_subagent_setup.py --restore            # latest
python3 codex_deepseek_subagent_setup.py --restore 20260809-123456-000000 --yes
python3 codex_deepseek_subagent_setup.py --dry-run --remove   # preview
python3 codex_deepseek_subagent_setup.py --remove --yes       # real removal
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | success or no-op |
| `1` | failure (write failure with automatic rollback, no backups found) |
| `2` | usage error or refusal (conflicting actions, unknown backup ID, destructive action without `--yes`/`--force`) |

## Backups and state

- A backup is created **before** every mutation and stored **outside the Codex
  home** (`~/.codex-backups/codex-deepseek-subagent/<timestamp>/`) so config
  switchers such as cc-switch, which swap `~/.codex`, never destroy them.
- Backups are **absence-aware**: the manifest lists every managed file,
  including files that were absent, so restore can delete installed extras.
- On a failed mutation the pre-change snapshot is restored automatically
  (rollback).
- `--restore` is an exact snapshot restore; ownership is restored from the
  snapshot too, so a pre-install snapshot leaves the home unowned again.
- `--remove` deletes only owned whole files/directories whose hashes match the
  recorded state (unless `--force`) and surgically removes only the owned
  `hooks.json` group, `[shell_environment_policy.set]` keys, and AGENTS marker
  block, preserving unrelated user bytes/content.

## Hook trust

Codex trusts the exact Hook definition hash and intentionally skips changed
command hooks until they are reviewed. When an install reports
`hook_review_required` (the Hook definition changed):

1. Open **Settings -> Hooks** in the Codex app.
2. Review the changed `^v4_flash_worker$` definition and trust it.
3. **Refresh** the hooks view.

Restart the app only as a fallback: hot reload is not guaranteed by the
official docs. The installer never writes a trust hash.

## Payload source of truth

The authoritative payload lives in `payload/` and mirrors the landed
`use-v4-flash-worker` skill tree. The single raw script embeds a byte-exact
copy (plus a per-file SHA-256 manifest) so `uv run <raw-url>` needs no clone.

```bash
# resync payload/ from the authoritative skill tree, then re-embed:
python scripts/sync_embedded_payload.py --source ~/.agents/codex/skills/use-v4-flash-worker

# re-embed after editing payload/:
python scripts/sync_embedded_payload.py
```

A parity test (`tests/test_payload.py`) fails when `payload/`, the embedded
copy, and the pyproject version drift.

## Development

```bash
uv run pytest        # or: python3 -m pytest
```

Tests cover payload integrity, credential preservation, the Hook shape,
config/AGENTS merging and surgical removal, absence-aware backup/restore,
rollback, remove ownership, Windows/macOS behavior, and the `~/.agents`
runtime boundary — all against temporary directories, nothing touches the
real Codex home.

## Security notes

- No API key or secret is stored in this repository.
- The agent file is written with mode `0600` on POSIX systems.
- The staged task text briefly exists as plaintext in local user state
  before being sent to the configured provider — the Hook is a transport
  compatibility layer, not a confidential channel.
