# SIM-1 bug hunt — `git diff main...HEAD` over hooks / skills / agents / references / quality / docs

Scope: `we/hooks/ we/scripts/ we/skills/ we/agents/ we/references/ we/quality/ docs/plan-format.md docs/skills.md`.
`docs/plans/SIM-1-context/` excluded. Findings only — nothing fixed.

Every hook finding marked *(reproduced)* was driven against the real module with a temp armed repo;
`we/hooks/test_verification_gate.py` is 52/52 green, so none of these is caught today.

**Count:** 3 high · 10 medium · 6 low.

---

## HIGH

### H1 — The plan's `## Verification` block cannot pass the gate that reads it

`docs/plan-format.md:170-173` prescribes `- **Assert:**` and `- **Not provable here:**`.
`we/skills/story/SKILL.md:189-191` and `we/references/verification.md:44-45` prescribe
`**Asserted:**` / `**Not proven:**` (plus `**Exit criterion:**`, which `plan-format.md` omits
entirely). The hook checks `_filled(body, "asserted")` (`we/hooks/verification_gate.py:283`).

`we/agents/pr-creator.md:61-70` orders the block copied **verbatim from
`docs/plans/${TICKET}-story.md` § Verification** and forbids authoring one. So a plan written to
plan-format v1.2, filled in honestly, is denied by the gate as *"a `## Verification` heading over
an unfilled receipt — the seed and the assertion are still the template's placeholders"*
**(reproduced)**. pr-creator's own escape hatch — "a refusal naming a mechanical fix … you fix once
and retry once; a second refusal is a stop" — turns a correct receipt into a stopped PR.
One block, three spellings, in a diff whose point was the receipt — and the same wave moved the
two files in **opposite** directions: `story/SKILL.md` was changed *from* `Not provable here:`
*to* `Not proven:`, while `plan-format.md` newly *introduced* `Not provable here:`.

### H2 — `cat <<'EOF' > pr-body.md` loses the redirect; a stale file then vouches for a new body

`we/hooks/verification_gate.py:36-38` — `_HEREDOC`'s `[^\n]*` swallows the remainder of the
opening line, redirect included. `_written_here` (`:120-131`) therefore finds no `>` token and
falls back to reading the path from disk.

Failure scenario **(reproduced)**: `cat <<'EOF' > pr-body.md … EOF` + `gh pr create --body-file
pr-body.md` with a receiptless body **and a leftover receipt-bearing `pr-body.md` on disk** →
ALLOW. The gate reads yesterday's receipt and waves today's claim through. With no file on disk it
fails open instead. Only `cat > file <<EOF` (the ordering `_write_then_create` in the tests pins)
works — `test_a_stale_file_does_not_outrank_the_body_being_written:374` pins the safe direction of
exactly this seam and misses the unsafe one.

### H3 — `static_analysis_passed` / `test_passed` have two owners, and a chunk worker writes them

The diff moved the owner column to **Lead** in `we/references/integration-pipeline.md:33-34`, but:
- `we/agents/static-analyzer.md:56-57` and `we/agents/test-runner.md:61-62` still write the
  checkpoints themselves;
- `we/references/integration-pipeline.md:96-97` still writes `static-analyzer →
  static_analysis_passed` (readable as "which gate feeds which checkpoint", so weaker evidence —
  but it is the line a reader lands on when dispatching);
- `we/agents/pr-creator.md:17-18` still names `/we:static` and `/we:test` as the writers.

Consequence, not just prose drift: `we/skills/develop/SKILL.md:110-118` spawns both agents **per
chunk**, on a `feat/{KEY}-p{N}` branch that carries the ticket key. The agent extracts `$TICKET`
from the branch and writes the integration-level checkpoint off one worker's partial, fast-tests-only
diff. `pr-creator.md:17-18` treats that checkpoint as blocking → the blocking gate is green before
the merged diff was ever gated.

---

## MEDIUM

### M1 — `pr_created` is never written: `$WE_ROOT` is out of scope

`we/agents/pr-creator.md:91` uses `"$WE_ROOT/scripts/orchestration.py"`, but `WE_ROOT` is derived
only in the Step 2 block at `:31`. Each Bash call is a fresh shell — the repo states this rule in
`we/skills/ci-review/SKILL.md:66`. Step 9 runs `python3 "/scripts/orchestration.py"`, fails, and
the checkpoint silently never lands. `we/agents/static-analyzer.md` and `test-runner.md` derive it
in the same block and are fine.

### M2 — The gate never checks `Not proven:`, though its own message demands it

`we/hooks/verification_gate.py:283` checks only `seed` and `asserted`. `_WHERE` (`:98-107`) and
`we/references/verification.md:45` both state `**Not proven:**` is required, and
`we/agents/ac-reviewer.md:97` makes it a Fail row. A receipt with Oracle+Seed+Asserted and no
`Not proven` passes **(reproduced)**. The one field that records what the oracle *cannot* show is
the unenforced one.

### M3 — A fenced `**Seed:**` block is stripped, and the receipt reads as unfilled

`we/hooks/verification_gate.py:250,255` — `_FENCE.sub("", body)` removes every fenced block before
the heading search. A receipt whose seed is a multi-line ```bash block (the natural shape, and the
shape `we/references/verification.md:39-46` itself uses to present the template) is denied as
"unfilled" **(reproduced)**. The quotation defence (`test_a_receipt_inside_a_fenced_block_is_a_quotation:416`)
has no counter-test for a receipt that legitimately *contains* a fence.

### M4 — The dispatch brief orders the old step sequence

`we/skills/orchestrate/SKILL.md:306` still dispatches
"implement → fast local gates → AC-check your diff → commit → push".
`we/references/worker-dispatch.md:52-59` and `we/skills/develop/SKILL.md` (Step 2 commit-per-phase →
Step 3 gates → Step 4 AC-check → Step 5 push) were rewritten to commit **before** the gates. A
worker following the brief and a worker following the skill produce different commit histories, and
`develop`'s "never `git add -A`, it would sweep `WORKER-REPORT.md`" reasoning only holds in the new
order.

### M5 — `develop` tells `static-analyzer` to do the opposite of its own contract

`we/skills/develop/SKILL.md:115` — `"Report findings; fix nothing."`
`we/agents/static-analyzer.md:47-49` Step 4 — "On a failure, run the stack's auto-fix
(`ruff check --fix` / `eslint --fix` / …) and re-check." One agent, two mandates in one dispatch.

### M6 — `dor-scan.md` documents a regex the code does not use

`we/references/dor-scan.md:20` claims the phase regex is `^### Phase \d+:` and calls it "the same
expression `_body_is_refined` uses". `we/scripts/orchestration.py:2670` is
`^### Phase \d+` — **no colon**. A plan with `### Phase 1 — Foo` is `refined` to the CLI and fails
a hand-run scan. The sentence was added in this diff specifically to assert the two agree, and
`we/skills/refine/SKILL.md:91` now tells refiners to `Grep` their own file for the colon form.

### M7 — `refined` has three writers under a "single owner" label, and the pointer is wrong

`we/quality/dor.md:101` — "`/we:story` Step 6 writes it (single owner of the command)".
`we/skills/story/SKILL.md` has no Step 6: its last step heading is `## Step 5: Post-Approval`
(`:260`), and the checkpoint is item 5 *inside* it (`:304`). Nor is it a single owner —
`we/skills/orchestrate/SKILL.md:96-99` ("write it now, whoever wrote the plan") and `:292`
(refine-lane batch) both write `refined` as well.

### M10 — `status: blocked` exists only in the format spec

`docs/plan-format.md:30` adds `blocked` to the `status` enum "while a `## Open Fork` section is
open". Both writers of such a plan say otherwise: `we/skills/refine/SKILL.md:32` — "leave
`status: draft`" — and `we/skills/orchestrate/SKILL.md:99` — "a plan with an open fork is
`draft`". No consumer implements it either: `we/scripts/orchestration.py:2964`
`EPIC_STATES = ("shipped", "integrated", "built", "refined", "draft", "idea")`, and `_classify`
(`:3075-3088`) derives the rung from evidence and can never return `blocked`. A refiner following
the format spec produces a status nothing reads.

### M8 — `review.cross` means two different things

`we/references/worker-dispatch.md:80-82` (changed here) — "`review.cross` governs only this
per-chunk pass; the bug-hunt below always runs once at integration."
Still selecting the bug-hunt engine by `review.cross`: `we/CLAUDE.md:23`,
`we/skills/setup/SKILL.md:176,179`, `docs/workflow.md:109`. Setting `review.cross: false` therefore
either keeps the bug-hunt or silently drops it, depending on which file the reader loaded.

### M9 — `docs/skills.md` drops ci-review's concrete-reason exception

`docs/skills.md:170` — "without one it stops after the first pass and asks."
`we/skills/ci-review/SKILL.md:55-58` and `:264-266` — re-enter Phase 4 without a user budget on a
concrete reason (unsure fix, flaky check, interdependent findings, high-stakes PR), "loop at most
twice". The summary states a stricter rule than the skill.

---

## LOW

### L1 — `gh` with a global flag before the verb bypasses the gate entirely

`we/hooks/verification_gate.py:190` requires `argv[i+1:i+3] == ["pr","create"]`.
`gh -R owner/repo pr create --body-file b.md` and `gh --repo o/r pr create --fill` are never seen
**(reproduced)**. Same class: `bash -c "gh pr create …"` and `echo $(gh pr create …)` — the latter
despite `_pr_verb`'s `lstrip("({")`, which does not strip `$(`.

### L2 — `_written_here` matches on basename only

`we/hooks/verification_gate.py:125` — a heredoc redirected to `notes/pr-body.md` satisfies
`--body-file pr-body.md`. A receipt written into an unrelated file vouches for the PR body.

### L3 — `_cwd_after_cd` scans past the `gh` call

`we/hooks/verification_gate.py:134-139` walks the whole argv, so `gh pr create --body-file b.md &&
cd apps` relocates the lookup for a command that already ran in the old cwd. Related: a body-file
token carrying a trailing separator (`--body-file b.md; fi`) makes the read fail → fail-open
**(reproduced)**.

### L4 — `WE_ROOT` fallback is silently empty when the glob misses

`we/agents/static-analyzer.md:56`, `test-runner.md:61`, `integration-pipeline.md:40` —
`$(ls -d ~/.claude/plugins/cache/*/we/[0-9]* | ...)` on no match yields the empty string, so the
checkpoint call becomes `python3 "/scripts/orchestration.py"`: a no-op that looks like a run.

### L5 — `<plugin-root>` survives in one place

`we/skills/story/SKILL.md:304` still writes `python3 <plugin-root>/scripts/orchestration.py` while
every other checkpoint call in this diff moved to the `WE_ROOT` derivation — the exact token
commit 7cad15a set out to remove.

### L6 — `Exit criterion:` is prescribed but unspecified

`we/references/long-running.md:70` puts it in the plan's `## Verification` block;
`we/skills/story/SKILL.md:191` emits it; `docs/plan-format.md:170-173` — the format spec — does not
list it. Third field of the same block missing from the spec (see H1).
