# codex-deepseek-subagent-setup

Cross-platform, idempotent installer for the **DeepSeek V4 Flash worker** in
Codex: a custom subagent that runs on `deepseek-v4-flash` while the main
agent keeps its own model, provider, and login untouched.

Built around the [codex-deepseek-subagent](https://github.com/Utopia-V/codex-deepseek-subagent)
plaintext-Hook workflow, plus local customizations:

- agent file with the `[model_providers.deepseek]` block (base URL + bearer
  token resolved at runtime, never hard-coded)
- `sandbox_mode = "danger-full-access"` (full access for the worker)
- `[features.multi_agent_v2]` block
  (`hide_spawn_agent_metadata = false`, `tool_namespace = "agents"`) in
  `config.toml`
- routing + task-handoff blocks in the Codex global `AGENTS.md`
- the `use-v4-flash-worker` skill, including the task-handoff integration
  section

## What it manages

| File | Content |
|---|---|
| `agents/v4-flash-worker.toml` | custom agent: `deepseek-v4-flash`, provider `deepseek`, full sandbox |
| `skills/use-v4-flash-worker/` | `SKILL.md` + `agents/openai.yaml` |
| `hooks/codex-deepseek-subagent/plaintext_handoff.py` | handoff script, SHA-256 verified |
| `hooks.json` | `SubagentStart` Hook (matcher `^v4_flash_worker$`), merged, no trust hash |
| `config.toml` | `[features.multi_agent_v2]` block, text-level idempotent |
| `AGENTS.md` | routing + task-handoff blocks, marker-based idempotent |

## Quick start

Requires Python 3.11+ (and optionally [uv](https://docs.astral.sh/uv/)).

```bash
# one-shot, no clone (uv):
uv run --refresh https://raw.githubusercontent.com/DaqiHu/codex-deepseek-subagent-setup/main/codex_deepseek_subagent_setup.py

# or install as a tool (uv):
uv tool install git+https://github.com/DaqiHu/codex-deepseek-subagent-setup

# or clone and run:
git clone https://github.com/DaqiHu/codex-deepseek-subagent-setup
cd codex-deepseek-subagent-setup
python3 codex_deepseek_subagent_setup.py
```

The installer prompts for base URL and API key on a TTY (press Enter to
auto-resolve). Resolution order:

1. explicit interactive input (key is echoed while typing)
2. `~/.kimi-code/config.toml` → `[providers.opencode-go]` (base URL + token)
3. fallback: official `https://api.deepseek.com` + `DEEPSEEK_API_KEY` env var

The key is never embedded in the repository and never printed.

## Options

```text
-h, --help            show help and exit
--dry-run             preview changes; nothing is written or backed up
--backup-dir PATH     backup directory (default: ~/.codex-backups/codex-deepseek-subagent)
--skip-backup         do not create a pre-change backup snapshot
--restore [ID]        restore from a backup timestamp or "latest" (default)
--manual              print the full manual
```

Backups are stored **outside the Codex home**
(`~/.codex-backups/codex-deepseek-subagent/<timestamp>/`) so that config
switchers such as cc-switch, which swap `~/.codex`, never destroy them.

## After a successful run

1. Fully restart the ChatGPT app / Codex process.
2. Open `/hooks` and trust the `SubagentStart` definition (the installer
   never writes a trust hash).
3. Start a NEW task.
4. Optionally run the quick-smoke-test flow
   (`prompts/quick-smoke-test.md` from the upstream repo) for a real
   end-to-end check.

## Development

```bash
uv run pytest        # or: python3 -m pytest
```

Tests cover credential resolution, TOML/JSON generation, hook merging,
config/AGENTS.md injection, backup/restore, and idempotence, all against
temporary directories — nothing touches the real Codex home.

## Security notes

- No API key or secret is stored in this repository.
- The agent file is written with mode `0600` on POSIX systems.
- The staged task text briefly exists as plaintext in local user state
  before being sent to the configured provider — the Hook is a transport
  compatibility layer, not a confidential channel.

## Upstream

- Protocol and handoff scripts: https://github.com/Utopia-V/codex-deepseek-subagent
- DeepSeek Responses API: https://api-docs.deepseek.com/zh-cn/guides/responses_api
