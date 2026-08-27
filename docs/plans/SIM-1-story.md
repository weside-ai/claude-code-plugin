---
type: story-plan
story: SIM-1
created: 2026-08-27
status: approved
parallel_groups: [[1, 2, 3, 4]]
---

# Plan: Simulate and cut the four skill clusters `/we:orchestrate` depends on

## Context

Plugin 5.4.0 rebuilt `/we:orchestrate` from a 30-day usage scan and three rounds of Opus
table-top simulation (weside-core `docs/plans/WA-2087-context/plugin-usage-scan.md`; method:
read the skill and its references completely, trace every tool call against a concrete world
state without executing, list defects adversarially, grade 1–5, re-judge the previous round).
Round 1 found 50 defects a read-through had missed. The same method is now applied to the
skills the Lead dispatches to or relies on, in the order that closes the loop with the new
orchestrate first: the worker skills that receive its briefs, then the most-used and
most-interrupted skill, then the plan-writer whose output orchestrate consumes, then the
pipeline agents behind the gates. Opus 5 needs fewer instructions than these skills carry —
the goal is fewer lines that steer, not more lines. Every chunk ends with the skill *shorter*
than it started unless a simulation proved a mechanic missing.

## Acceptance Criteria

1. **Given** a chunk's skill files **When** the chunk finishes **Then** each has been simulated
   in at least two rounds by a fresh Opus agent (round N+1 re-judges round N), the final grade
   is ≥ 4/5 for every scenario, and the reports live in `docs/plans/SIM-1-context/<chunk>/`.
2. **Given** the revised files **When** `python3 scripts/validate-consistency.py` runs **Then**
   it passes, and no skill body grew except where a report names the missing mechanic.
3. **Given** a defect that needs a change in a file outside the chunk's list **When** the worker
   finds it **Then** it is reported as a fork to the Lead, never edited.

## User Journey

Technical only. The next Lead dispatches a worker, the worker follows `/we:develop` from the
Lead's brief without inventing a step; the next `/we:ci-review` run ends in ≤ 3 rounds without
the human typing "was ist das review gate".

## Testing Requirements

- `python3 scripts/validate-consistency.py` green after every chunk.
- Simulation reports with round-over-round verdict tables.

## Verification

- **Oracle:** substitute — the simulation grade and the consistency check; behaviour of a live
  run is measured later by `scripts/harness/plugin-usage-scan.py` in the host repo.
- **Seed:** none (documents only).
- **Assert:** every scenario ≥ 4/5 in the final round; `validate-consistency.py` exit 0.
- **Not provable here:** that a live worker/Lead behaves as simulated — the next real
  `/we:orchestrate` wave in the host repo is the observation.

### Receipt (2026-08-27, integration e5ffa3c)

- **Oracle:** substitute — per-chunk final-round grades read from
  `docs/plans/SIM-1-context/*/`, `python3 scripts/validate-consistency.py`, `python3 -m pytest
  we/hooks -q`.
- **Seed:** `git checkout feat/SIM-1-integration` at e5ffa3c.
- **Asserted:** develop+refine a 4 · b 4 · c 4 · d 5 (3 rounds) · ci-review a 4 · b 4 · c 4.5 · d 4.5
  (4 rounds) · story a 4 · b 4 · c 4 · d 4 (4 rounds) · gates A 4 · B 4 · C 4 · D 4 (3 rounds);
  consistency PASSED; 52 hook tests passed.
- **Not proven:** live behaviour of the four skills — observed on the next real wave; the five
  post-grade edits in ci-review and the Lead's glue commit were not re-simulated.

## Technical Approach

**Patterns:** table-top simulation (scenarios with concrete world state, trace not execute);
`.claude/rules/plugin-authoring.md` (single owner, no no-ops, paired negations); references are
read-only for workers — a fix there is a fork.

## Implementation Phases

### Phase 1: `develop` + `refine` — the worker side of the briefs

- **Goal:** a worker spawned with the 5.4.0 Refiner-/Worker-Brief runs the skill without
  inventing a step; the skills are shorter.
- **Files:** `we/skills/develop/SKILL.md`, `we/skills/refine/SKILL.md`,
  `we/references/dor-scan.md`, `docs/plans/SIM-1-context/workers/`.
- **Approach:** Scenarios: (a) Agent worker with a Mode-B brief (`--phases 2`, worktree path
  given, critical chunk with integration suite, `WORKER-REPORT.md`); (b) worker with a
  whole-story brief and `parallel_groups` in the plan; (c) refiner with a front-loaded context
  that hits a design fork; (d) refiner whose plan fails the DoR scan once. The simulator plays
  the worker, not the Lead. Cut what Opus 5 does unprompted; keep the reporting contract.

### Phase 2: `ci-review`

- **Goal:** 153 calls / 38 interrupts in 30 days become a skill that ends in ≤ 3 rounds and
  says what the review gate is; shorter.
- **Files:** `we/skills/ci-review/SKILL.md`, `docs/plans/SIM-1-context/ci-review/`.
- **Approach:** Scenarios: (a) `codex-review` red with `VERDICT:ERROR` and no finding;
  (b) `ci-core-fired` pending behind a merge conflict; (c) CodeRabbit + claude-review threads,
  one factually wrong WARNING; (d) "automerge aktiviert, mache /ci-review bis merged, max 3
  Runden". The known-CI-states table in weside-core's `ci-workflow.md` must end up with ONE
  home — report as a fork which side keeps it.

### Phase 3: `story`

- **Goal:** the plan `story` writes carries what 5.4.0 orchestrate reads — `parallel_groups`
  with stated semantics, `## Verification` as the receipt's home, the repo DoR read — and the
  skill is shorter.
- **Files:** `we/skills/story/SKILL.md`, `we/references/long-running.md`,
  `we/references/ticket-briefs.md`, `docs/plans/SIM-1-context/story/`.
- **Approach:** Scenarios: (a) refine an existing ticket with contradicting comments;
  (b) create-mode from a vague sentence; (c) a story that is really an epic; (d) the emitted
  plan is fed to a simulated `/we:orchestrate` Step 0–5 — does the Lead need anything the plan
  does not carry?

### Phase 4: pipeline gates — `ac-reviewer`, `pr-creator`, `verification_gate.py`

- **Goal:** one merged diff with a violated DoD row and a missing receipt is stopped at the
  right gate with the right message; 104 hook blocks in 30 days become fewer, not louder.
- **Files:** `we/agents/ac-reviewer.md`, `we/agents/pr-creator.md`,
  `we/hooks/verification_gate.py`, `we/quality/dod.md`, `docs/plans/SIM-1-context/gates/`.
- **Approach:** Scenarios: (a) diff passes ACs, fails one repo DoD row; (b) receipt missing,
  `verification.required: true`; (c) receipt present in the plan's `## Verification` but not
  in the PR body; (d) mixed-authorship wave. Add a pytest matrix for the hook if none exists.

## Design Decisions

| Decision | Alternatives Considered | Why This |
|---|---|---|
| Four parallel chunks on Opus | serial, or Sonnet workers | files are disjoint; a simulator needs the top tier — the whole method rests on its judgement |
| References read-only for workers | let workers edit shared references | two chunks would edit `worker-dispatch.md`; forks to the Lead keep one writer |
| Run under `/we:orchestrate` 5.4.0 in this repo | run inline | it is the first live test of the rebuilt skill, including the no-`.weside/orchestrate.md` fallback |

## Code Guidance

**DO:** read every file completely before the first scenario; two rounds minimum; shorten.
**DON'T:** edit files outside the chunk's list; add prose Opus 5 does not need; execute the
skill under test.

## Security Review Required

No.

## Documentation Impact

- **Docstrings** — n/a
- **Generated** — `docs/skills.md` if a flag or invocation changed (fork to the Lead).
