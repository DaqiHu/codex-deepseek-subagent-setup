---
acceptance_criteria:
- The unrelated-hooks removal reproduction passes with zero unrelated data loss.
- Malformed TOML cannot be generated from credentials, validation/state failures rollback
  and exit 1, and strict add cannot claim skipped files.
- All review/verification findings listed in the instructions are covered by tests
  and pass.
agent_type: v4_flash_worker
allowed_paths:
- G:\GitHub\codex-deepseek-subagent-setup-wt-installer-lifecycle\codex_deepseek_subagent_setup.py
- G:\GitHub\codex-deepseek-subagent-setup-wt-installer-lifecycle\scripts\sync_embedded_payload.py
- G:\GitHub\codex-deepseek-subagent-setup-wt-installer-lifecycle\tests
- G:\GitHub\codex-deepseek-subagent-setup-wt-installer-lifecycle\README.md
- G:\GitHub\codex-deepseek-subagent-setup-wt-installer-lifecycle\.kanpd\docs\tasks
bypass_format_check: true
completed_at: null
created_at: '2026-08-09T09:07:11Z'
domains:
- python
- agent-tooling
format_version: 2
mode: implementation
model: deepseek-v4-flash
parent_task: null
prohibited_repos: []
result_summary: null
reuse_count: 0
review_round: 0
status: draft
task_kind: impl
verification:
- uv run --python 3.11 pytest -q
- uv run --python 3.12 pytest -q
- uv run --python 3.12 python scripts/sync_embedded_payload.py --check
verify_round: 0
worktree_path: G:\GitHub\codex-deepseek-subagent-setup-wt-installer-lifecycle
---
# Objective

Fix all verified lifecycle safety and correctness findings after review of ad5dc30

## Worktree Directives

- This task is bound to an assigned worktree. All writes and modifications
  MUST happen inside this worktree:
  `G:\GitHub\codex-deepseek-subagent-setup-wt-installer-lifecycle`
- You MUST NOT modify any file outside the assigned worktree, unless the
  user explicitly instructs otherwise.
- Before any write, verify the anchor once: run
  `git -C G:\GitHub\codex-deepseek-subagent-setup-wt-installer-lifecycle rev-parse --show-toplevel` (must equal
  `G:\GitHub\codex-deepseek-subagent-setup-wt-installer-lifecycle`) and check `git -C G:\GitHub\codex-deepseek-subagent-setup-wt-installer-lifecycle status`.
- Use absolute paths inside the worktree for every Edit / Write / command.
- Committing inside the assigned worktree is pre-authorized by the
  worktree usage contract; merging back to the primary checkout is part
  of task delivery.

## Context

Independent review and verify task Results identify blocking findings in ad5dc30. Fix exact issues with RED tests and commit. Do not expand architecture.

## Files to Read

- ~/.agents/skills/task-handoff/SKILL.md
- ~/.agents/skills/task-handoff/references/cache-optimization.md
- ~/.agents/skills/task-handoff/references/domain/full-stack-typescript.md
- ~/.agents/skills/task-handoff/references/domain/game-design-notes.md
- ~/.agents/skills/task-handoff/references/domain/python.md
- ~/.agents/skills/task-handoff/references/domain/unreal-engine.md
- ~/.agents/skills/task-handoff/references/evidence-and-intent.md
- ~/.agents/skills/task-handoff/references/human-intervention.md
- ~/.agents/skills/task-handoff/references/parallel-optimization.md
- ~/.agents/skills/task-handoff/references/skill-dev/execution-time.md
- ~/.agents/skills/task-handoff/references/tier/l.md
- ~/.agents/skills/task-handoff/references/tier/m.md
- ~/.agents/skills/task-handoff/references/tier/s.md
- ~/.agents/skills/task-handoff/references/tier/xl.md
- ~/.agents/skills/task-handoff/references/tier/xs.md
- G:/GitHub/codex-deepseek-subagent-setup-wt-installer-lifecycle/.kanpd/docs/tasks/task-260809-085300-installer-lifecycle-review.md
- G:/GitHub/codex-deepseek-subagent-setup-wt-installer-lifecycle/.kanpd/docs/tasks/task-260809-085336-installer-lifecycle-verify.md
- G:/GitHub/codex-deepseek-subagent-setup-wt-installer-lifecycle/codex_deepseek_subagent_setup.py
- G:/GitHub/codex-deepseek-subagent-setup-wt-installer-lifecycle/tests/test_remove.py
- G:/GitHub/codex-deepseek-subagent-setup-wt-installer-lifecycle/tests/test_lifecycle.py

## Instructions

1. Add RED tests reproducing every required fix before editing code.
2. Fix remove_hook_group so a pre-existing hooks.json with unrelated groups or top-level content is never deleted merely because its post-install whole-file hash matches state; remove only the owned matcher group, and delete the file only when it is provably an installer-created shell with no unrelated content.
3. TOML-escape user/existing/kimi credentials and base URLs safely. Make validate return success/failure; include writes, state save, and validation inside one rollback-protected transaction, returning exit 1 after rollback on any failure.
4. Make --add atomic and strict: if any managed existing artifact conflicts, return exit 2 and write/state-own nothing. Never record ownership for content the action skipped.
5. Add sync_embedded_payload.py --check that is read-only and exits nonzero on payload/embed/version drift; update docs/tests.
6. Make restore of an absent snapshot entry honor --yes as documented; expose the pre-restore safety backup ID; make status compare the current Hook to the installed state hash so changing the Python used to run status does not create a false trust alert.
7. Preserve an existing env_key credential configuration on noninteractive update instead of switching to a kimi token. Add JSON usage-error coverage if it is a small localized change.
8. Run Python 3.11 and 3.12 full suites, sync --check, raw CLI smokes, linter, and git diff --check. Commit fixes and write four-section Result with exact evidence.

## Acceptance Criteria

1. The unrelated-hooks removal reproduction passes with zero unrelated data loss.
2. Malformed TOML cannot be generated from credentials, validation/state failures rollback and exit 1, and strict add cannot claim skipped files.
3. All review/verification findings listed in the instructions are covered by tests and pass.

## Constraints

1. Work only in assigned worktree; never mutate live user homes; all probes use temporary paths. Do not modify payload files in this task.
2. You are not alone; preserve the committed implementation and do not revert unrelated changes.
3. Allowed to modify: G:\GitHub\codex-deepseek-subagent-setup-wt-installer-lifecycle\codex_deepseek_subagent_setup.py, G:\GitHub\codex-deepseek-subagent-setup-wt-installer-lifecycle\scripts\sync_embedded_payload.py, G:\GitHub\codex-deepseek-subagent-setup-wt-installer-lifecycle\tests, G:\GitHub\codex-deepseek-subagent-setup-wt-installer-lifecycle\README.md, G:\GitHub\codex-deepseek-subagent-setup-wt-installer-lifecycle\.kanpd\docs\tasks
4. Assigned worktree: G:\GitHub\codex-deepseek-subagent-setup-wt-installer-lifecycle

## Result

### Findings

All review/verify findings fixed in the assigned worktree with RED tests first
(`tests/test_lifecycle_fixes.py`, 24 tests: 20 RED-failed on ad5dc30, 4 guard
tests) and committed after full verification.

1. **hooks.json unrelated-data loss (verify FAILURE, blocking)** - fixed.
   `remove_hook_group` now deletes `hooks.json` only when the current bytes
   match the recorded state hash AND removing the owned matcher group leaves no
   unrelated content (new `_hooks_document_has_unrelated_content` helper:
   other top-level keys, a different `description`, other hook categories, or
   remaining SubagentStart groups all count as unrelated). A pre-existing,
   installer-merged hooks.json is surgically edited instead. The same
   ownership guard was aligned in the non-dry-run delete branches of
   `remove_config_owned` / `remove_agents_block` (they previously deleted when
   the remaining text was empty even without a state-hash match; the dry-run
   branches already required ownership). E2E reproduction (seeded
   `description="user hooks"` + `^other$` group): install -> `--remove --yes`
   -> file survives, owned group gone, unrelated group and description intact,
   bytes changed. Tests:
   `test_remove_preserves_preinstalled_hooks_json`,
   `test_remove_preserves_preinstalled_hooks_other_category`,
   `test_remove_deletes_installer_created_hooks_json`.
2. **Validation ignored; exit 0 on broken install (review F1, High)** - fixed.
   `validate()` now returns `bool`; `_run_install` runs writes, state save, and
   post-write validation inside one rollback-protected transaction: any write /
   state-save / validation failure rolls back the pre-change snapshot and
   returns exit 1. A no-op run with pre-existing malformed managed files also
   returns exit 1 (validation_failed) instead of reporting success. Tests:
   `test_validate_returns_true_for_valid_home`,
   `test_validate_returns_false_for_broken_config`,
   `test_install_rolls_back_and_exits_1_on_validation_failure`; raw CLI smoke
   `--install` after corrupting `config.toml` exits 1.
3. **Malformed TOML from credentials (review F1 root cause)** - fixed. New
   `toml_string()` (JSON escaping, a valid TOML basic-string subset) escapes
   user, existing, and kimi credentials plus base URLs everywhere they are
   emitted; `agent_toml_content` escapes `base_url`. Tests:
   `test_toml_string_escapes_special_characters`,
   `test_agent_toml_escapes_base_url_and_credentials`,
   `test_resolve_credentials_escapes_user_input`.
4. **`--add` not atomic/strict (review Concern + instruction 4)** - fixed.
   `_plan_changes` collects `conflicts` for any managed artifact that exists
   and would change (whole files, hooks.json without an identical owned group,
   config.toml/AGENTS.md that would be modified); `--add` with a conflict
   returns exit 2, writes nothing, creates no backup, and saves no state, so it
   never claims ownership of skipped content. Identical pre-existing artifacts
   remain a clean no-op (exit 0). Tests:
   `test_add_conflict_exits_2_and_writes_nothing`,
   `test_add_agents_md_without_block_is_conflict`,
   `test_add_hooks_json_without_group_is_conflict`,
   `test_add_identical_partial_files_are_not_conflicts`; existing
   `test_add_never_overwrites_existing` updated to the new exit-2 contract;
   raw CLI smoke confirms exit 2 with nothing written.
5. **`sync_embedded_payload.py --check` missing (verify Concern 1)** - fixed.
   Added a read-only `--check` mode (`check_drift()` regenerates the embedded
   block from `payload/` + pyproject version and compares it to the installer;
   exits 1 on any drift incl. manual edits to the embedded block, without
   writing). Tests: `test_sync_check_exits_zero_on_committed_tree`,
   `test_sync_check_detects_payload_drift`,
   `test_sync_check_detects_version_drift`; CLI run exits 0 on the tree.
6. **Restore absent-branch ignores `--yes` (verify Concern 2)** - fixed:
   `_plan_restore` now deletes a drifted installed extra when `--yes` is passed
   (previously only `--force`), matching the refusal message and README. Tests:
   `test_restore_yes_deletes_drifted_installed_extra`,
   `test_restore_without_yes_refuses_drifted_extra`.
7. **Pre-restore safety backup ID not surfaced (review F4)** - fixed:
   `cmd_restore` captures the safety snapshot, prints a BACKUP status, and adds
   `safety_backup_id` (distinct from the source `backup_id`) to the JSON
   result. Test: `test_restore_reports_safety_backup_id`; raw CLI smoke.
8. **False trust alert when status runs with a different Python (review F5)** -
   fixed: `cmd_status` compares the live Hook group against the
   interpreter-independent `hook_definition_sha256` recorded in state, falling
   back to the payload-desired comparison only when no recorded hash exists.
   Tests: `test_status_no_false_alert_with_different_python`,
   `test_status_detects_real_hook_change`.
9. **env_key credential mechanism drift on update (review Concern)** - fixed:
   `_existing_agent_credentials` now preserves an `env_key` entry (base_url +
   key) as well as a bearer token; a noninteractive update keeps the existing
   mechanism instead of switching to the `~/.kimi-code` fallback token. Tests:
   `test_existing_agent_credentials_env_key`,
   `test_update_preserves_env_key_credential`; raw CLI smoke.
10. **JSON usage errors (review F3)** - fixed: conflicting-action refusal emits
    a JSON object on stdout with `exit_code: 2` when `--json` is set. Test:
    `test_conflicting_actions_json`.

### Concerns

- `--add` records state hashes for pre-existing files whose content is already
  byte-identical to owned content; this cannot cause unrelated-data loss
  because every whole-file deletion still requires a state-hash match and the
  partial-file removers require a hash match plus no remaining unrelated
  content.
- `validate()` still does not check AGENTS.md content or hook-script
  executability; a trailing-comment duplicate-section edge case in
  `merge_config` is out of scope for this fix round.
- uv recreated the gitignored `.venv` during 3.11 verification runs (normal
  uv behavior, committed tree unchanged).

### Alternatives

- For the hooks.json delete decision: tracking per-file pre-existence in state
  at install time was considered; the content-based "no unrelated content"
  check was chosen because it is robust to older states that lack a
  pre-existence flag and cannot misclassify any file that carries unrelated
  bytes.
- For status: comparing only payload-owned hook fields was considered; the
  recorded `hook_definition_sha256` comparison was chosen because it is exact,
  interpreter-independent, and already persisted.

### Open Questions

- None blocking. A follow-up could file the now-fixed hooks.json defect against
  the upstream repo (outside `agents`/`kanpd`, so no standing `gh issue
  create` authority applied).
