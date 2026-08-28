# SIM-1 — state

## Right now

Wave 1 closed 2026-08-28 00:05 UTC. **PR #43 open** (<https://github.com/weside-ai/claude-code-plugin/pull/43>), squash-merge requested; one ci-review pass: CI ruff PLC0415 fixed in 6ef36e2. Waiting on the human's merge → Step 10 (remove integration worktree + branches, plugin update to 5.5.0, `/reload-plugins`). Teammates torn down; chunk worktrees removed.

Wave 1 dispatched 2026-08-27 ~22:50 UTC by the Lead (host-repo session, /we:orchestrate 5.4.0).
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

(none for the human — merge #43)

## Orchestrate 5.4.0 — live observations for the next cut

- Step 5.7: cut the chunk worktrees only after the integration branch verifiably carries the plan (my plan commit failed markdownlint and the worktrees were cut without it).
- A worker's Bash commit that trips an auto-fixing pre-commit hook aborts silently; `git log -1` after every commit (the host repo's rule) belongs in the Worker-Brief.
- Simplify/AC/docs/bug-hunt as Agents each cost 5–10 min; the bug-hunt re-ran itself (round 2) and overwrote its report while the Lead was fixing round 1 — a report file needs a round suffix or the agent must not rewrite.
- Bug-hunt round 1 carried 5 harness artefacts (shared tmp repo); "one fresh repo per case" belongs in the code-review brief for hooks.
- The Lead squashed p2 before merging to keep host-repo names out of history; a public-repo leak scan belongs in Step 8 A for repos that declare themselves public.

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

p4 (gates), integrated 525046c — grades A 4, B 4, C 4, D 4; ac-reviewer −8 %, pr-creator −1 %, dod.md −2 %, hook 5.2k → 12.6k + 14.8k test matrix (50 tests). Hook now blocks `gh pr create --fill`; `--web`/MCP-opened PRs stay ungated (docstring):
9. `integration-pipeline.md` names three blocking checkpoints before the PR, pr-creator four (`ac_verified`) — align the reference to four.
10. `integration-pipeline.md` § Quality gates restates the bug-hunt matrix without the mixed-authorship case — replace with a pointer to `worker-dispatch.md`.
11. Same section: `/code-review` is a skill and would run in the Lead's context — wrap in `Agent()`.
12. Checkpoint table credits `static_analysis_passed`/`test_passed` to the agents; orchestrate says every checkpoint is the Lead's — align.
13. `worker-dispatch.md`: `review.cross` governs the bug-hunt and, next clause, does not; its matrix keys on `tools.codex` — align to `execution.default` + `tools.codex`.
14. Per-chunk AC-check is required of headless workers that cannot run it; `.reviews/` is branch-keyed — drop the per-chunk requirement for detached backends.
15. `verification.md` consumer list omits `pr-creator`.
16. `orchestration.py` stores a checkpoint as a bare name — `--evidence` proposed (tool follow-up, not this wave).

p2 (ci-review), integrated a8d8fc9 (worker's two commits squashed by the Lead so the internal names in commit 1 never reach history) — grades a 4, b 4, c 4.5, d 4.5; 335 → 295 lines; five report-named fixes landed after the last graded round, un-simulated:
17. Known-CI-states table exists only in the host repo's `ci-workflow.md` (brief premise wrong) — host keeps it, plugin carries the generic mechanic; no change.
18. `integration-pipeline.md` § "One ci-review pass" re-implements the procedure for the Lead with an unbounded "wait for CI" (scenario b deadlock) — Lead glue: point it at the skill's gate definition and terminal states.
19. `quality/dod.md` carries a third copy of the severity scale — Lead glue.
20. `docs/skills.md` § ci-review "max 2 cycles" vs. user budget — Lead glue.
21. Leak scan over the integrated tree: `apps/backend|apps/mobile` paths in all sim fixtures (generic host-app names, not this repo's rule-compliant) — Lead neutralises at Step 8 B; pre-existing hits in `handoff/SKILL.md:221` and `test_ready_set.py` are out of scope.

p3 (story), integrated 6bc7fa4 — grades a 4, b 4, c 4, d 4 (4 rounds); story 21.6k → 18.7k; long-running +380, ticket-briefs +190 (report-named):
22. `docs/plan-format.md` missing `type`/`epic`/`## Verification`, no `blocked`, parallel_groups without cap — Lead glue (1.2).
23. `quality/dor.md`: `${CLAUDE_PLUGIN_ROOT}` in a shell block, duplicate checkpoint block, "parent Epic" row unsatisfiable on GitHub Issues — Lead glue.
24. `ticketing.md` defines no `{TICKET}` for GitHub Issues / plan-only — Lead glue.
25. orchestrate Step 0: a single key with `epic:` flipped to the Epic path — Lead glue.
26. Frontmatter inline `#` comments are parsed as values by `_parse_frontmatter` — templates ship bare now; `orchestration.py` unchanged (tool follow-up).
27. Unsettled by design: `/we:story` Step 5 commits the plan to `main` without a consent gate — `po-altitude.md` sets that convention for all Plan skills; changing it is one decision across four skills, not this wave's.

Pipeline (Lead): simplify → nothing (d0cd109 later formatted the test file only) · AC+DoD gate BLOCKING on AC 2 (refine +32 %, ~800 B unbought) → cut to 7.3k (709bd00) → ac_verified · static ✓ · tests 133 → 62 hook tests after the bug-hunt fixes · bug-hunt (`/code-review high` in an Agent): 3 high / 10 medium / 6 low, all closed in 3b59e42 (H1 receipt field names in plan-format, H2 heredoc redirect lost → stale file vouched, H3 agents wrote integration checkpoints from chunk diffs) · docs pass: 5 corrections applied (bbab94c, 0e7f4f0) · version 5.5.0.

## Verification log

p1: validate-consistency ✓ after merge 313bcf8. p4: consistency ✓, pytest 50 ✓ after merge 525046c. p2: consistency ✓ after merge a8d8fc9. p3: consistency ✓ after merge 6bc7fa4. Integration 3b59e42: consistency ✓, pre-commit ✓, pytest we/hooks 62 ✓, we/scripts ✓.
