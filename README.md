> [!IMPORTANT]
> **DEPRECATED / ARCHIVED.** This repository is no longer an active source or
> authority and accepts no new features. It is retained only for history.
> **DaqiHu/agents is the only active authority** for the Codex
> `v4_flash_worker` installer, runtime skill, and Hook
> (`codex/skills/use-v4-flash-worker/`).

# codex-deepseek-subagent-setup

This repository previously hosted a self-contained installer for the Codex
`v4_flash_worker` subagent. That capability now lives solely in
`DaqiHu/agents` — `codex/skills/use-v4-flash-worker/scripts/install.py` —
and this repository is retained only for history.

## Install from DaqiHu/agents

The agents repository is the single authoritative source. Install from a clone
of the agents repository:

```powershell
uv run python "<repo>\codex\skills\use-v4-flash-worker\scripts\install.py"
```

or one-shot from the raw GitHub source without a clone (the agents repository
carries no LFS payloads, so the raw path is reliable):

```powershell
uv run python "https://raw.githubusercontent.com/DaqiHu/agents/main/codex/skills/use-v4-flash-worker/scripts/install.py"
```

Verify the installation and ownership deterministically without writing
anything:

```powershell
uv run python "<repo>\codex\skills\use-v4-flash-worker\scripts\install.py" --status --json
```

`--status --json` compares every installed file, the Hook definition, the
marked Codex AGENTS block, and the shell environment against the agents
source, and exits `0` only when the installation is complete and owned by
agents (`"status": "installed"`, `"owned": true`). A missing or drifted
file exits `14` with `"status": "missing"` or `"status": "drift"`;
re-run the installer to refresh `CODEX_HOME`.

## Migrate from this repository

Machines provisioned by this repository migrate in one step: run the agents
installer above (it migrates the legacy AGENTS block and replaces the Hook),
then remove the old tool entry:

```powershell
uv tool uninstall codex-deepseek-subagent-setup
```

Existing
`uv tool install git+https://github.com/DaqiHu/codex-deepseek-subagent-setup`
and `uvx --from codex-deepseek-subagent-setup ...` references must be
replaced by the agents installer commands above.