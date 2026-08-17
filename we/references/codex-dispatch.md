---
name: codex-dispatch-reference
description: The single-detach Codex dispatch rule + chunk-brief template, in one place. Referenced by /we:codex-task and /we:orchestrate. Loaded on demand.
---

# Codex Dispatch — single-detach rule + chunk brief

Codex (`gpt-5-codex`) is an **optional** execution backend driven through the
official Codex plugin's `codex-companion.mjs task` runtime
([openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc)). The `we`
plugin never hard-depends on it — absent the `codex` CLI, everything runs on
Claude Code Agent teammates. This reference is the **one** place the dispatch
mechanics live; `/we:codex-task` and `/we:orchestrate` both link here.

## The one rule that bites: pick exactly one backgrounding mechanism

`node codex-companion.mjs task --write --background …` **already detaches** the
job itself (and registers it for `/codex:status`). Additionally wrapping that
call in Bash `run_in_background: true` **double-detaches** — the companion's job
is orphaned, the work never runs, the worktree stays empty, and `/codex:status`
cannot see it (confirmed failure 2026-06). So pick exactly one:

- **Want `/codex:status` tracking** → companion `--background`, Bash **foreground**
  (the call returns at once with a `task-…` id, so it does not block the turn).
- **Want the harness completion-notification for a long chunk** → companion
  **foreground** (no `--background`), wrapped in Bash `run_in_background: true`.

Never `--background` **and** Bash background together.

## Resolve the runtime

```bash
CODEX_COMPANION=$(ls -d ~/.claude/plugins/cache/openai-codex/codex/*/scripts/codex-companion.mjs | sort -V | tail -1)
```

## Dispatch shape

```bash
# Status-tracked background (single detach via the companion):
node "$CODEX_COMPANION" task --write --background --cwd "<chunk worktree>" "<chunk brief>"

# Long foreground chunk with harness notification (single detach via Bash):
node "$CODEX_COMPANION" task --write --cwd "<chunk worktree>" "<chunk brief>"   # + Bash run_in_background: true
```

Always pass `--cwd <chunk worktree>` so Codex writes into the chunk's isolated
worktree, never the main one.

## Verify before trusting "done"

A lost dispatch reports success while writing nothing. Before integrating, the
Lead **verifies the worktree actually changed** (`git -C <worktree> status` /
`git -C <worktree> log`) — never trust a "done" without commits or a dirty tree.

## There is no way to talk to a running Codex worker

`codex-companion.mjs task` is a detached process, not a teammate. It has no
inbound channel: `SendMessage` does not reach it, and `/we:orchestrate` Step 7's
"nudge the builder, at most once" applies to Agent teammates only. Whatever you
learn after dispatch — a namespace collision, a seam you just found, a file it
must not touch — cannot be delivered.

So the brief is the whole instrument:

- **Front-load.** Anything you would have said at minute ten belongs in the text
  before dispatch. When in doubt, over-specify: a Codex worker follows a written
  constraint well and invents nothing to replace a missing one.
- **Turn unsendable rules into merge-time checks.** Write down, at dispatch, the
  command that will verify each constraint you cannot enforce live. A verified
  constraint is stronger than a message anyway.
- **Watch the artifacts, not the process.** `git -C <worktree> status --porcelain
  | wc -l` a minute in tells you the dispatch landed and the worker is writing;
  an empty tree after several minutes is the lost-dispatch signal above.
- **A FULL tree with no commit is the other failure, and it is the expensive
  one.** Codex can finish the work correctly and die before committing — no
  error, no message, nothing to observe but a dirty worktree that looks
  identical to one still being written. Measured 2026-08-17: a complete,
  well-built chunk sat unnoticed for ten hours while the Lead reported "still
  running", because a watcher waited on a commit that could never come and
  `pgrep -af codex` was counting the Lead's own shells (they carry the Codex env
  vars). Only the human asking twice surfaced it.

  So **never wait on the commit.** Arm the wait on `git status --porcelain`
  going non-empty AND a timeout — when the timeout fires, read the worktree
  yourself: if the work is there, verify and commit it (crediting the worker in
  the trailer and saying in the body that the Lead committed it). A Codex worker
  has no liveness signal in either direction, so the Lead's timeout IS the
  signal. An Agent teammate needs none of this: it reports or it is reported
  terminated.

This is the one real trade against an Agent teammate. Pick Codex when the brief
can be complete, an Agent when the shape may change under the worker.

## Chunk brief template (Mode-B)

Codex gets the same focused brief an Agent teammate would, scoped to one chunk:

```
Worktree: <absolute path to the chunk worktree, already on the chunk branch>
Goal: <one phase / one coherent slice — what "done" means>
Files: <the files this chunk owns; do NOT touch anything outside>
Constraints: <conventions, primitives to compose, anti-patterns to avoid>
Pins: <existing behaviour to preserve exactly; surface forks, do not invent>
Done = <concrete, checkable outcome — tests green / file:line exists / command exits 0>
Report back: <what to surface — the diff summary + any fork decision>, do NOT open a PR.
```

The Lead reviews each returned diff, integrates onto the one integration branch,
runs QS once → one PR, human merges. Identical to the Agent-teammate path apart
from who implements the chunk.

## Generated-artifact constraints to spell out in the brief

A Codex worker only edits what you tell it to. Two generated-artifact traps recur and need an
explicit `Constraints:` line when the chunk touches them:

- **OpenAPI/types:** after a change to a Pydantic schema referenced by a route (request/response
  model), the worker MUST regenerate AND commit **both** specs (`poetry run python
  scripts/generate-openapi.py` → `openapi.json` + the client spec) in addition to
  `yarn ... generate:types`. The OpenAPI-Types CI check regenerates TS **from the committed spec**,
  so committing only the `.ts` (or only the schema) leaves a stale spec and fails CI — and a full
  local spec regen in a bare worktree can emit formatting noise, forcing a hand-edit. Tell the
  worker to commit the spec, not just the types.
- **Frontend gates can't run in a fresh worktree** (no `node_modules`, ~1 GB) — the worker
  implements frontend changes but does NOT run `yarn`/`jest`/`tsc`; it reports the skipped frontend
  validation and the Lead validates via CI. (Same applies to the Agent-teammate path.)
