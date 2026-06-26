---
name: codex-dispatch-reference
description: The single-detach Codex dispatch rule + chunk-brief template, in one place. Referenced by /codex:task and the /we:orchestrate Mode-B executor-selection section. Loaded on demand.
---

# Codex Dispatch — single-detach rule + chunk brief

Codex (`gpt-5-codex`) is an **optional** execution backend driven through the
official Codex plugin's `codex-companion.mjs task` runtime
([openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc)). The `we`
plugin never hard-depends on it — absent the `codex` CLI, everything runs on
Claude Code Agent teammates. This reference is the **one** place the dispatch
mechanics live; `/codex:task` and `/we:orchestrate` Mode-B both link here.

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
