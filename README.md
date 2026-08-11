> [!IMPORTANT]
> **No longer the active authority.** This repository is no longer the active
> source or authority for the Codex `v4_flash_worker` installer, runtime
> skill, and Hook; it has not been deprecated or archived yet.
> **DaqiHu/agents is the only active authority**
> (`codex/skills/use-v4-flash-worker/`). Formal GitHub archiving of this
> repository is the parent's remaining step, and until it lands this
> repository stays live.

# codex-deepseek-subagent-setup

This repository previously hosted a self-contained installer for the Codex
`v4_flash_worker` subagent. That capability now lives solely in
`DaqiHu/agents` — `codex/skills/use-v4-flash-worker/scripts/install.py` —
and this repository stays live until the parent formally archives it.

## Install from DaqiHu/agents

The agents repository is the single authoritative source. Install from a
clone or any local checkout of the agents repository (`DaqiHu/agents` is
private, so there is no unauthenticated one-shot raw URL; `uv run python
"<url>"` only accepts local file paths):

```powershell
uv run python "<repo>\codex\skills\use-v4-flash-worker\scripts\install.py"
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
re-run the installer to refresh `CODEX_HOME`. `--json` is accepted for
compatibility and the installer always emits JSON, so the documented
command above works verbatim.

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