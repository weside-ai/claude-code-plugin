# AC Review: feat/SIM-1-integration

Reviewed at `e5ffa3c` (+ receipt commit) against `main`. 71 files, 19998 insertions — the bulk
is simulation evidence under `docs/plans/SIM-1-context/`, not deliverable. No prior review for
this branch (`.reviews/` absent), so this is V1, not a delta review.

## Summary

AC 1 and AC 3 hold against the files: every chunk's final-round grade is ≥ 4/5 and I read them
in the reports rather than trusting the receipt, and no worker commit touched a file outside its
chunk's list. AC 2 fails: `we/skills/refine/SKILL.md` grew 6506 → 8591 B (+32 %), and the chunk's
own final-round report itemises ≥ 675 B of that growth as **unbought** — not as a mechanic a
simulation proved missing — and calls one of the added blocks "actively wrong".

## AC-Alignment

| AC | Status | Evidence |
|----|--------|----------|
| 1 — ≥ 2 rounds per chunk, final grade ≥ 4/5 per scenario, reports in `SIM-1-context/<chunk>/` | **Met** | Final-round grades read from the files, not the receipt: `workers/round2-scenario-a.md:268` **4/5** · `workers/round2-scenario-b.md:234` **4/5** · `workers/round3-scenario-c.md:226` **4/5** · `workers/round3-scenario-d.md:260` **5/5** · `ci-review/round3-scenarios-a-c.md:336,341` **A 4/5, C 4.5/5** · `ci-review/round4-scenario-b.md:280` **4/5** (round 3 was 3.5, so round 4 is the final round and it clears the bar) · `ci-review/round3-scenario-d.md` **4.5/5** · `story/round4-a-…:563` **4/5** · `story/round2-b-…:603` **4/5** · `story/round2-c-…:659` **4/5** · `story/round2-d-…:607` **4/5** · `gates/round3-{a,b,c,d}` **4** each (frontmatter `grade: 4` on b/c/d, prose on a:243). Every scenario has ≥ 2 rounds; all reports live under `docs/plans/SIM-1-context/<chunk>/`. The receipt's numbers reproduce exactly. |
| 2 — `validate-consistency.py` passes; no skill body grew except where a report names the missing mechanic | **NOT MET** | Consistency half passes: `python3 scripts/validate-consistency.py` → `PASSED: All consistency checks OK`, exit 0. The growth half fails on `we/skills/refine/SKILL.md`, 6506 → 8591 B (+32.0 %). Its own final-round report `workers/round3-scenario-c.md:200-219` prices the additions and names what is not bought: the `status: draft` clause (~175 B) is tabled as "**no named finding** — defensible … but unbought", and "The ~500 bytes round 2 already called unbought are all still present: the step-0 `MISSING:` re-dispatch paragraph (~250) and the uncut aphorisms (~250)". The report escalates the first: "Round 3 upgrades the first from dead weight to **actively wrong** — that paragraph is the block that creates N4". `docs/plans/SIM-1-state.md` records the same fact in the Lead's own words: "refine +32 % (~500 B unbought)". The report also names the remedy: "A tighter revision that cuts the aphorisms and generalises step 0 lands this same content near 7800." A report that calls growth *unbought* is the opposite of a report that *names the missing mechanic* — the AC's test is not met, on either the literal or the purposive reading. (The report's own byte arithmetic ends at 8327 against an actual 8591; the file has a single commit, so HEAD is the graded state and the unbought total is ≥ 675 B. This strengthens the same row, it is not a second one.) |
| 3 — a defect outside the chunk's file list is reported as a fork, never edited | **Met** | Per-commit file lists (`git show --name-only`, glue commit `e5ffa3c` exempt): p1 → `develop/SKILL.md`, `refine/SKILL.md` only · p2 → `ci-review/SKILL.md` only · p3 → `story/SKILL.md`, `references/long-running.md`, `references/ticket-briefs.md` only · p4 → `agents/ac-reviewer.md`, `agents/pr-creator.md`, `hooks/verification_gate.py`, `hooks/test_verification_gate.py`, `quality/dod.md` only. Every path is in that chunk's plan `**Files:**`; `test_verification_gate.py` is authorised by Phase 4's own Approach ("Add a pytest matrix for the hook if none exists"). 21 forks are logged in `SIM-1-state.md` and closed in the glue commit, which is where every out-of-list file (`references/dor-scan.md`, `worker-dispatch.md`, `integration-pipeline.md`, `orchestrate/SKILL.md`, `plan-format.md`, `docs/skills.md`, …) changed. |

**Feature reachable:** n/a — documents and one hook; the hook is wired via `we/hooks/`.
**End-to-end:** yes for what is provable here — `validate-consistency.py` exit 0 and 52 hook
tests green over the integrated tree; live behaviour of the four skills is explicitly deferred.

## DoD Quick Check

| Criterion | Status | Note |
|-----------|--------|------|
| Architecture patterns followed | Pass | `.claude/rules/plugin-authoring.md` shape kept; references stayed read-only for workers, all cross-file fixes routed through the Lead's glue commit. |
| ACs individually verified | Fail | AC 2 unmet — see the row above. |
| Every planned phase landed | Pass | All four phases' `**Files:**` changed. One exception to name in the PR body: Phase 1's `we/references/dor-scan.md` changed only in the Lead's glue commit `e5ffa3c`, not in p1's — the reason is fork #1 (real owner differs from the plan's path, and the text drifts from `_body_is_refined`). The DoD requires that attribution be stated in the PR body; it is not written yet. |
| Security patterns applied | N/A | Plan: Security Review Required = No. |
| State wiring complete | N/A | No data field crosses layers. |
| Tests verify behaviour | Pass | `python3 -m pytest we/hooks -q` → **52 passed**. New matrix `we/hooks/test_verification_gate.py` (15.5 kB) asserts hook decisions, not merely that a call returned. |
| **Verification (observed, not inferred)** | Pass | The plan carries a `## Verification` block with a dated `### Receipt (2026-08-27, integration e5ffa3c)`: oracle **substitute** (per-chunk final-round grades + `validate-consistency.py` + `pytest we/hooks`) with the reason stated in the AC section ("behaviour of a live run is measured later by `scripts/harness/plugin-usage-scan.py`"), seed `git checkout feat/SIM-1-integration` at e5ffa3c, the asserted grades and gate results enumerated, and *Not proven* naming both the live behaviour and the un-re-simulated post-grade edits. I re-ran both oracles myself and they reproduce. A substitute with its reason is a pass; the disclosure of un-re-simulated edits is what a receipt is for and is not converted into a second Fail here. |
| Success claims carry their output | Pass | Receipt states counts; both commands re-run in this review with their output quoted. |
| Deliberate bypasses justified | N/A | No bypass convention in this repo; no new annotations in the diff. |
| Horizontal scalability | N/A | No server-side process-local state; the hook is a per-invocation CLI process. |
| No open TODO/FIXME | Pass | `git diff main...HEAD -- we/ docs/plan-format.md docs/skills.md \| grep '^+.*(TODO\|FIXME)'` → no hits. |
| Generated artefacts regenerated | Pass | `docs/skills.md` § ci-review updated to the new cycle-cap wording (fork #20). |
| Documentation Impact addressed | Pass | Plan's Documentation Impact named `docs/skills.md` as a fork to the Lead; it landed in the glue commit. |
| Repo-local DoD additions | N/A | No `.weside/dod.md` in this repo. |

## Not blocking, but owed before the PR

- The locked decision "version bump 5.4.0 → 5.5.0" (`SIM-1-state.md`) is not in the diff.
- The PR body must name Phase 1's `dor-scan.md` as Lead-committed, with fork #1 as the reason.

## Verdict

<!-- VERDICT:BLOCKING -->
