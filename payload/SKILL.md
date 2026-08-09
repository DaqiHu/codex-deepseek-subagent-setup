---
name: use-v4-flash-worker
description: Use when Codex considers spawning, continuing, or troubleshooting the DeepSeek-backed v4_flash_worker, including plaintext Hook staging, Windows Python encoding, task-handoff contracts, transport recovery, or the external DeepSeek data boundary.
---

# Use V4 Flash Worker

## Choose the worker

- This default is a standing user override: dispatch `v4_flash_worker` by
  default for any independently bounded research, documentation,
  implementation, review, or test/log-analysis task, including bounded text,
  code, log, search, extraction, enumeration, and high-volume reading whose
  raw material is much larger than the conclusion. task-handoff tiers still
  control contracts and quality gates, but a non-visual implementation with
  an independently definable v4 slice is not kept in the main agent on tier
  grounds. One-step XS work with no meaningful separable slice is done
  directly by the main agent; this is a granularity limit, not a provider
  exception.
- Use the available concurrency slots: batch independent slices into one
  parallel round, and keep decomposition, verification, and final integration
  in the parent.
- Native vision multimodality is the primary main-agent exception: only work
  that requires image understanding stays in the main agent or a multimodal
  worker. Tasks that need no image understanding are never delayed by this
  exception.
- Private repositories and sources are covered by standing authorization from
  the personal installation and the Codex AGENTS routing block; private or
  confidential provenance alone is not a reason to re-ask or refuse.
- Keep real secrets and tokens out of assignments. Redact or minimize
  credentials, tokens, personal, and regulated data so the payload carries
  only what the task needs; the safe remainder is delegated normally.

## Verify the installation

The version-controlled source lives at `codex/skills/use-v4-flash-worker` in
the agents repository and is intentionally not discovered from `~/.agents`, so
shared cross-agent environments never see it. Run the installer after copying
or updating this skill. It selects the current Python executable for the
Windows Hook, installs an explicit `commandWindows`, sets `PYTHONUTF8=1` and
`PYTHONIOENCODING=utf-8` in Codex's shell environment, publishes the single
runtime skill to `~/.codex/skills/use-v4-flash-worker`, copies the Hook to
`~/.codex/hooks/codex-deepseek-subagent/plaintext_handoff.py`, and idempotently
synchronizes the marked Codex AGENTS block into `~/.codex/AGENTS.md` while
preserving unrelated content:

```powershell
uv run python "<skill-dir>\scripts\install.py"
```

If the installer reports `hook_review_required: true`, review the changed Hook
with `/hooks`. Codex trusts the exact Hook definition hash and intentionally
skips changed command hooks until the user reviews them. The result also
reports `agents_block_updated` so you can confirm the `~/.codex/AGENTS.md`
sync.

## Deliver one self-contained job

1. Build one complete assignment containing child identity, objective, scope,
   exclusions, permissions, evidence or output contract, and stopping condition.
2. Stage it through the installed handoff script. On Windows PowerShell, make
   the native pipe UTF-8 explicitly even when the current session predates the
   installed Codex environment settings. Codex Desktop supplies
   `CODEX_THREAD_ID`; staging refuses to publish without that identity so one
   desktop task can never occupy or feed another task's pending slot:

   ```powershell
   $OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
   $env:PYTHONUTF8 = "1"
   $env:PYTHONIOENCODING = "utf-8"
   $assignment | python -X utf8 "<codex-home>\hooks\codex-deepseek-subagent\plaintext_handoff.py" --mode stage
   ```

   On macOS or Linux, use:

   ```shell
   printf '%s' "$assignment" | python3 -X utf8 "<codex-home>/hooks/codex-deepseek-subagent/plaintext_handoff.py" --mode stage
   ```

   When the named launcher is unavailable, inspect the effective
   `SubagentStart` Hook matching `^v4_flash_worker$`, reuse its reviewed Python
   executable, and change only `--mode hook` to `--mode stage`.
   Outside Codex Desktop, `--session-id <id>` may be used only when that exact
   id will appear as `session_id` in the matching `SubagentStart` Hook input.
3. Require a successful JSON stage result naming `v4_flash_worker`. The script
   publishes pending state atomically under a hashed per-thread path, so a
   failed serialization or write leaves no partial pending JSON and concurrent
   Codex tasks never block or consume each other's assignments. The raw thread
   id and assignment body are never included in routing diagnostics.
4. Immediately spawn the exact agent type `v4_flash_worker` with a unique task
   name and `fork_turns="none"`. The spawn message may point to the one-shot Hook
   but the staged assignment remains the complete source of instructions. Spawn
   independent workers in one parallel batch when the concurrency slots allow.
5. Use one task-sized native idle wait or callback. Verify the contribution in
   proportion to the parent claim, then integrate it in the parent context.

## Deliver follow-ups by fresh spawn only

Codex Hook events fire only when a session or subagent starts: `SubagentStart`
runs at spawn, and no documented Hook event fires for `followup_task` or
`send_message`. A follow-up message therefore never re-triggers the plaintext
Hook, and the child would receive only the provider-internal collaboration
ciphertext. Never use `followup_task` or `send_message` to deliver a new or
continued `v4_flash_worker` assignment. For every new or continued task, stage
a complete self-contained contract and spawn a fresh `v4_flash_worker` with
`fork_turns="none"`. The same channels remain fine for ordinary non-task status
or coordination messages (for example "start now" or an acknowledgement) that
carry no assignment content.

## Bound the assignment

The installed Hook keeps `additionalContextLimit` at `0` (per the Codex docs,
the only setting that passes the complete context without a truncated preview)
and enforces a strict hook-side output cap instead: `plaintext_handoff.py
--mode stage` refuses assignments larger than `MAX_ASSIGNMENT_BYTES_DEFAULT`
(32 KiB) with exit code 11 and publishes no pending state. Reduce the
assignment or split it into a fresh spawn, then restage. The Hook `timeout` is
60 seconds (the Codex documented default is 600); the script only reads a small
local file, so a hung Hook still fails fast.

## Integrate task-handoff contracts

When the parent uses `task-handoff`, stage the full contract rather than only
its path. Include Objective, Context, Files to Read, Instructions, Acceptance
Criteria, Constraints, the absolute audit path, child boundary, output contract,
and stopping condition.

Ask the worker to fill the pinned `## Result` headings: Findings, Concerns,
Alternatives, and Open Questions. Frontmatter remains parent-owned. Tier
classification, quality gates, archiving, and disk audit also remain in the
parent; this Hook transports the contract but does not duplicate its lifecycle.

## Write the task Result deterministically

When `apply_patch` cannot launch on the child (for example the WindowsApps
shim is missing), do not improvise a bespoke edit. Use the bundled writer,
which replaces only the `## Result` section of the task file:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$result | python "<skill-dir>\scripts\update_task_result.py" --task "<absolute task path>"
```

The writer reads the four-section Result from stdin and requires the pinned
headings `### Findings`, `### Concerns`, `### Alternatives`, and
`### Open Questions` to appear exactly once, in that order. It rejects any
malformed, reordered, or missing input with exit code 2 before touching the
task file. A successful run preserves every byte before `## Result` -
frontmatter, body, and LF line endings - and writes the replacement
atomically, so a failed write never leaves a truncated task. Frontmatter
stays parent-owned; the writer never edits anything outside the Result
section.

## Edit implementation files when apply_patch cannot launch

Keep the built-in `apply_patch` tool as the primary path for editing ordinary
implementation files. When it cannot launch on the child (for example the
WindowsApps shim fails with `Access is denied`), use the bundled
`apply_patch.py` fallback instead of improvising a Python or PowerShell
full-file rewrite:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$diff | python "<skill-dir>\scripts\apply_patch.py" --root "<worktree root>"
```

The fallback reads a standard unified diff from stdin and applies it atomically
inside the `--root` directory (the assigned worktree). Produce the diff with
`git diff`, or write the unified format directly: `--- <old path>`,
`+++ <new path>`, and `@@` hunks with `-`, `+`, and context lines. Create a
file with `--- /dev/null` plus `+++ <path>`; delete one with `--- <path>`
plus `+++ /dev/null`.

Empty-file creation uses the same create form with no `@@` hunk (an explicit
no-op `@@ -0,0 +0,0 @@` hunk is also accepted) and writes a zero-byte file.
Note that `git diff` prints no file headers for a newly added empty file, so
write the `--- /dev/null` / `+++ <path>` form directly for that case.
Pure-insertion hunks follow standard unified-diff numbering: `@@ -N,0
+N+1,1 @@` inserts before old line `N+1`, exactly like `git diff -U0` output.

The fallback is deterministic and constrained:

- Targets must stay under `--root`: absolute paths, drive-relative paths,
  `..` traversal, and any resolved target outside the root are rejected
  before anything is written.
- Every hunk is applied in memory first. Malformed patches, context
  mismatches, and unsupported markers such as
  `\ No newline at end of file` fail with a non-zero exit code and no
  partial write.
- The write phase stages temporary files and backs up existing targets, so a
  failure restores every file it already replaced.
- Content is strict UTF-8: CJK text is preserved, new files use LF, and
  modified files keep their dominant line ending.

Exit codes: `0` applied, `2` invalid patch, `3` could not apply or write,
`10` patch input was not valid UTF-8. When in doubt, generate the diff with
`git diff` so the hunk line numbers and counts are always exact.

## Recover transport failures

- Treat missing assignment, failed stage, unreadable task, or absent callback as
  a transport failure. Continue in the parent without silently substituting a
  provider, direct API call, inherited history, or another transport.
- Pending state is session-scoped: stage derives a hashed routing key from
  `CODEX_THREAD_ID`, and the Hook derives the same key from its trusted
  `session_id` input. A Hook with no matching per-session item returns without
  claiming anything. Missing identities fail explicitly (exit 12). Never scan,
  select, delete, or consume another session's pending item.
- Legacy unscoped `v4_flash_worker.pending.json` files are deliberately ignored
  by the session-scoped Hook. Preserve them for inspection or let an operator
  move them aside; never re-enable global fallback because it can cross-deliver
  private contracts between concurrent Codex tasks.
- An unconsumed valid item may be replaced only after expiry. Unreadable state is
  preserved for inspection and never overwritten automatically.
- A transient `FileExistsError` during staging is a publication race: a
  concurrent stage won, and its pending may already have been consumed by the
  hook. The script republishes exactly once, and only when no pending handoff
  survives. A real pending handoff is never overwritten; the refusal stays in
  place until it is consumed or expires.
- If essential instructions change after staging, wait for consumption or
  expiry, then stage a new self-contained assignment and spawn a fresh child.
- The assignment briefly exists as plaintext in local user state before being
  sent to DeepSeek. The Hook is a compatibility transport, not a confidential
  channel.

## Common Mistakes

| Mistake | Why it happens | Fix |
|---|---|---|
| Pipe UTF-8 text into cp936 Python | Windows PowerShell and Python inherited different encodings | Use the Windows staging recipe; the installed script also reconfigures all protocol streams to UTF-8 |
| Invoke `python3` unconditionally on Windows | POSIX examples are copied into a Windows Hook | Use `commandWindows` generated from the resolved installer interpreter |
| Write directly to the final pending file | Exclusive creation looks concurrency-safe but a failed write leaves truncated JSON | Serialize and fsync a temporary file, then publish it atomically without replacement |
| Use one global pending file across Codex tasks | Another session can consume the contract between stage and spawn | Bind stage to `CODEX_THREAD_ID` and let `SubagentStart.session_id` claim only the matching hashed per-thread pending path; never fall back to a global item |
| Edit Hook configuration without review | The script changed successfully, so the Hook appears ready | Open `/hooks` and trust the exact changed definition |
| Send only a task-file path | The cross-provider child may not have reliable inherited context | Stage the complete self-contained contract and retain the path only as an audit anchor |
| Send a new or continued assignment via `followup_task`/`send_message` | No Hook event fires for those channels, so the child gets only ciphertext | Stage a complete contract and spawn a fresh `v4_flash_worker` every time; keep those channels for non-task status messages only |
| Improvise a bespoke task edit when `apply_patch` is missing | The WindowsApps launcher is absent, so the child writes the Result ad hoc | Run the bundled `update_task_result.py` fallback, which validates the pinned headings and replaces only `## Result` |
| Rewrite an implementation file with an ad-hoc script when `apply_patch` is missing | The WindowsApps launcher is absent, so the child edits the whole file imperatively | Run the bundled `apply_patch.py` fallback with `--root` set to the assigned worktree; the built-in `apply_patch` stays the primary edit path |
| Refuse delegation because the task touches a private repository or source | Private provenance was mistaken for a per-task authorization gate | Standing authorization from the personal installation and the Codex AGENTS routing block covers task-relevant private sources; delegate with a payload scoped to the task |
| Send real secrets or tokens in the assignment | Minimization was skipped to save a step | Redact or substitute placeholders and delegate the safe remainder; a redacted payload only shrinks the assignment |
