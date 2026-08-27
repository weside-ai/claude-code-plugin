# SIM-1 — state

## Right now

Wave 1 dispatched 2026-08-27 ~22:50 UTC by the Lead (weside-core session, /we:orchestrate 5.4.0).
Integration: worktree `~/weside/claude-code-plugin-SIM-1-integration`, branch `feat/SIM-1-integration`.

## Dispatches

| chunk | worker | backend/model | branch | worktree | gate list |
|---|---|---|---|---|---|
| p1 develop+refine | worker-SIM-1-p1 | Agent opus | feat/SIM-1-p1 | ~/weside/claude-code-plugin-SIM-1-p1 | validate-consistency.py, pre-commit markdownlint |
| p2 ci-review | worker-SIM-1-p2 | Agent opus | feat/SIM-1-p2 | ~/weside/claude-code-plugin-SIM-1-p2 | same |
| p3 story | worker-SIM-1-p3 | Agent opus | feat/SIM-1-p3 | ~/weside/claude-code-plugin-SIM-1-p3 | same |
| p4 gates | worker-SIM-1-p4 | Agent opus | feat/SIM-1-p4 | ~/weside/claude-code-plugin-SIM-1-p4 | same + pytest we/hooks |

## Decisions locked

- Develop cap raised 2→4: doc-only chunks, pairwise-disjoint file lists, no build.
- All workers Opus (human: no Fable); no Codex (not configured here).
- References (`we/references/*`, `we/quality/*` except dod.md in p4) are read-only for workers; edits there are forks.
- Final PR against main with version bump 5.4.0 → 5.5.0.
- `.weside/orchestrate.md` absent in this repo — derived from CLAUDE.md; offer to write it at close-out.

## Open decisions

(none)

## Verification log

(pending)
