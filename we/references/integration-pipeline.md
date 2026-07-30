---
name: integration-pipeline
description: The steps that turn implemented code into a reviewed PR — simplify, AC+DoD gate, verification, the parallel quality gates, docs, PR, one CI pass, ticket to In Review. Single owner of the integration half of the story lifecycle. Loaded by /we:orchestrate.
type: reference
---

# The integration pipeline

Implementation ends when the code is committed and pushed. **This file owns everything after
that**, up to the point a human takes over: one PR, reviewed, CI green, ticket in review.

It runs **once per integration** — once per solo story, once per wave of workers. Running it
per worker is what the integration branch exists to prevent: N workers cost N dev budgets and
**one** CI, not N pipelines.

Who executes it: the session holding the whole (the Lead in `/we:orchestrate`). Workers never
run these steps — see `worker-dispatch.md` for what a worker does and stops doing.

## Checkpoints — the whole story lifecycle

`STORY_PHASES` in `scripts/orchestration.py` is the executed list; this table says who writes
each one. A checkpoint is a *durable* record — write it when the thing actually happened, not
when it was dispatched.

| Phase | Written when | Written by |
|---|---|---|
| `refined` | the plan passes the DoR scan (`dor-scan.md`) | Lead, after verifying — never the refiner |
| `git_prepared` | branch + worktree exist, ticket moved to In Progress | Lead at dispatch |
| `implementation_complete` | every phase committed and pushed | Lead, on the worker's report |
| `simplified` | § Simplify done | Lead |
| `ac_verified` | § AC + DoD gate passed **and** the verification block exists | Lead |
| `review_passed` | the one bug-hunt engine came back clean | Lead |
| `static_analysis_passed` | lint/format/types clean | `static-analyzer` |
| `test_passed` | tests green (coverage met where measured) | `test-runner` |
| `docs_updated` | doc proposals applied, or "nothing to update" | Lead |
| `pr_created` | the one PR is open | `pr-creator` |
| `ci_passed` | the single ci-review pass finished | Lead |

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint {TICKET} {phase}
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story status {TICKET}
```

---

## Simplify

Invoke `Skill(skill="simplify")`. Availability was verified once by `/we:setup` — trust that
gate; the only legitimate skip is the Skill tool actually answering "skill not found", in which
case warn `"simplify skill not available — run /we:setup to verify prerequisites"` and continue.
Changes made → commit. Checkpoint `simplified`.

**Simplify runs before the AC gate on purpose.** It can still move code — reuse, dead-code
removal, altitude cleanup. Verifying acceptance criteria against code that is about to be
rewritten spends the verification twice; verify once, against what will actually ship.

## AC + DoD gate (blocking)

Fresh-load the plan and the ticket (including its comments — `ticketing.md`). Verify **every**
acceptance criterion against concrete evidence: a file path, a test name, a commit. Check the
flow end to end — is the feature reachable?

Run `we:ac-reviewer` once against the full diff; the AC-review rule and its per-chunk vs.
at-integration split live in `worker-dispatch.md` § AC-review. The DoD table it fills comes
from `quality/dod.md` plus `<repo>/.weside/dod.md` where the repo has one — both apply, the
repo file adds and never replaces. **Any DoD `Fail` blocks exactly like a failed AC.**

**An AC worded "the full suite is green" is not an instruction to run the full suite here.**
Answer it with cheap targeted evidence — affected tests plus a reference-grep for orphaned
symbols. The suite runs in full exactly once, below, in the parallel gates; CI is the second,
independent confirmation. A third full run costs minutes and buys no signal (and on a large
repo exhausts local resources — observed: Postgres `out of shared memory` from one giant run).

## Verification — observe it, don't infer it (blocking)

Every gate so far is self-referential: tests written for code by whoever wrote the code, checked
by whoever briefed them. Run the result against a **running instance** per
`verification.md`, which owns the oracle ladder and the receipt format. In short: read
`<repo>/.weside/verify.md`, cover the user-visible journeys this change claims, DEV first —
**staging is a question to the user, not a step** — and write the `## Verification` block now,
because the PR body needs it and a repo that armed `verification.required` refuses `gh pr create`
without it.

A verification that did not happen is a blocking failure, exactly like a failed AC. "Tests are
green" does not discharge it.

Checkpoint `ac_verified` only when every AC passes, every DoD row passes, **and** the
verification block exists.

## Quality gates (parallel)

Launch all three in **one message** so they run concurrently:

- **`static-analyzer`** — lint, format, types → `static_analysis_passed`
- **`test-runner`** — tests + coverage → `test_passed`
- **one bug-hunt engine** → `review_passed`

**Exactly one bug-hunt engine runs, and the writer picks it: the engine that did *not* write the
code.** The full matrix (Claude wrote + Codex configured → `/codex:adversarial-review`;
otherwise Claude's native `/code-review`) is owned by `worker-dispatch.md` § Bug-hunt dispatch.
Codex answers with JSON rather than a marker — `approve` → write `review_passed`;
`needs-attention` → fix, re-run, then write it. Skip that mapping and the blocking gate in
`pr-creator` never gets set.

**No `we:ac-reviewer` call belongs here** — the AC gate above already ran it; this step hunts
bugs only.

**Install-gated gates run here too, not at CI.** Workers work in fresh worktrees with no
`node_modules`, so by design they skip every node-tool gate: prettier, eslint, tsc, jest,
dead-exports. The integration worktree is the one place in the run that can afford the install
— so install once and run them over the *merged* diff. Backend and architecture gates get the
same treatment even when each worker was green alone: merge-combined import edges break
import-linter baselines that no single diff did. Prefer hand-adding the new edges to
regenerating a baseline, which can strip annotations a contract test needs.

Letting CI catch these instead costs one full CI cycle **per failing gate class, serially** — an
observed run ate four (prettier → tsc → dead-exports → jest), each a ten-minute round trip.

Any gate red → fix and re-run. Three failures in the same phase opens the circuit breaker
(`orchestration.py circuit`), which stops and presents options rather than looping.

## Documentation

Always run. Dispatch the doc-architect and let it read the landscape fresh:

```python
Agent(
    subagent_type="we:doc-architect",
    description=f"Update documentation for {TICKET}",
    prompt=f"Story {TICKET} is implemented. Diff between this branch and the base: <summary>. "
           "Proactive mode: what documentation needs updating? Does this introduce or change a "
           "user-facing flow that wants a journey doc? Return file / change / why per item, or "
           "say explicitly that nothing needs updating.",
    run_in_background=True,
)
```

Present its proposals, apply the approved ones, commit, checkpoint `docs_updated`. It never
writes on its own — every change is a diff it waits for approval on. "Nothing needs updating"
is a complete answer; write the checkpoint and move on rather than inventing work.

If a bypass annotation changed and the repo ships `scripts/generate-bypass-register.sh`,
regenerate the register into the same docs commit.

## PR — one, and only after the gates

**Blocking:** `review_passed`, `static_analysis_passed` and `test_passed` must all exist.
Missing one → back to the gates. A PR with a failing gate wastes the reviewer's attention on
something the pipeline already knew.

```python
Agent(subagent_type="we:pr-creator", prompt=f"Create PR for {TICKET}")
```

This is the moment GitHub CI fires for the first time in the run — intentionally, on the
combined diff. Extract the PR number, checkpoint `pr_created`.

No GitHub remote → skip the PR and the CI pass; the local gates are then authoritative, and you
say so once rather than silently degrading.

## One ci-review pass — start early, hold the push

Execute this inline. **Never `Skill(skill="ci-review")`** — that loads the skill into the main
context and costs the Lead its overview; the procedure is short enough to run directly:

1. **Collect early**, as soon as the fast reviewers post — unresolved threads plus each bot's
   latest review body (every reviewer in `review.available`). Don't wait for the long CI to start.
2. **Triage and fix**: BLOCKING and WARNING must be fixed unless the reviewer is factually
   wrong; SUGGESTION and NITPICK are done or consciously skipped with a reason. Accumulate —
   don't commit or push between them.
3. **Wait for CI to conclude** (`gh pr checks {PR}` shows no `pending`/`in_progress`) and fold
   its failures into the same set.
4. Nothing found and CI green → checkpoint `ci_passed`, done.
5. **Commit** every fix as one commit.
6. **Resolve** every bot-authored thread via GraphQL and verify zero unresolved bot threads.
   Never auto-resolve a human's thread.
7. **Push once** — only now, so review-fixes and CI-fixes ship together.
8. Wait for the post-push CI to settle, report green or red, checkpoint `ci_passed`, **stop**.

**One pass, then stop.** Still red → report it and let the user decide whether to run
`/we:ci-review {PR}` again. Looping this automatically is how a run burns an afternoon on a
failure a human would have recognised in ten seconds.

## Ticket → In Review, and no further

Move every story that landed in this integration to In Review — detection, verify, retry-once
and soft-fail rules per `ticketing.md`. **Verify the move actually happened**; a transition that
silently failed is the failure mode this step exists for. If pushing reopened the ticket, move
it back.

**Leave it in In Review.** Done is the human's word after merge, and the Lead never merges.
