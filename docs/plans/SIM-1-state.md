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

(none for the human)

## Forks reported by workers (Lead glue at Step 8 B, or plugin follow-up)

p1 (develop+refine), integrated 313bcf8 — grades a 4, b 4, c 4, d 5; develop +2 %, refine +32 % (~500 B unbought):
1. Plan named `we/skills/refine/references/dor-scan.md`; real owner is `we/references/dor-scan.md`, which drifts from `_body_is_refined` (regex text vs code) — Lead fixes the reference text toward the code.
2. `docs/plan-format.md`: claims the scan reads the AC section; status enum lacks `blocked`; `## Open Fork` undefined — Lead glue.
3. orchestrate Worker-Brief hardcodes "AC-check your diff" while develop gates on `review.cross`; money-path wording duplicated — Lead glue in orchestrate.
4. `worker-dispatch.md` orders AC-check before commit; develop commits per phase, then gates, then AC-checks — Lead aligns the reference to the skill.
5. `worker-dispatch.md` + `test-discipline.md` claim sub-agents "cannot load references" — false; delete the claim.
6. `${CLAUDE_PLUGIN_ROOT}` has no fallback in a worker's Bash — Lead: state the cache path rule once.
7. A blocked plan (`## Open Fork`) passes the DoR scan mechanically → orchestrate Step 1 would checkpoint `refined`; orchestrate must treat `## Open Fork` as `draft` + Decision Queue.
8. Lead-rewritten plans (orchestrate Step 1) never clear `## Open Fork` — clause belongs in orchestrate.

## Verification log

p1: validate-consistency ✓ after merge 313bcf8.
