---
name: develop
description: >
  Dev-only worker slice — implements the assigned chunk, runs local quality
  gates, commits, pushes its branch, and STOPS (no PR, no CI loop, no ticket
  transition; the Lead integrates and runs CI once). Use when the user says
  "/we:develop", "implement only", "dev worker", "no PR", or when
  /we:orchestrate dispatches a chunk.
argument-hint: '[<ticket-key> | <plan-path>] [--phases <N,M>] [--engine <name>]'
---

# /we:develop — Dev-Only Worker Slice

Implement the assigned chunk, run local gates, commit, push, stop.

The difference from `/we:build`: no PR, no CI fix loop, no ticket transition.
The Lead (`/we:orchestrate`) integrates multiple workers onto one branch and runs CI **once**.
Use `/we:build` instead when you want the complete solo pipeline to a reviewable PR.

Full dispatch contract: [`${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md`](../../references/worker-dispatch.md)

---

## Step 0: Locate the plan

Resolve the plan file in priority order:

1. Explicit path argument → use as-is
2. Ticket key argument → `docs/plans/{KEY}-story.md`
3. No argument → look for an in-flight plan via `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story status` and pick the active one

**Frontmatter:** read `parallel_groups` to know which phases can run concurrently.
**`--phases N,M`:** restrict to those phase numbers only. If absent, run all phases.

Verify the plan has at least one `### Phase` header. If not, stop and tell the user.

---

## Step 1: DoR-lite check

Run the 3-item scan from `${CLAUDE_PLUGIN_ROOT}/references/dor-scan.md` (GWT ACs · Context > 50
chars · `### Phase` headers). If any item fails, stop and say which. This is lighter than
`/we:build`'s full DoR gate — the goal is to catch a completely un-refined plan, not to be a
final gate.

---

## Step 2: Worktree + branch

**If already in a dedicated worktree** (detected by: `git worktree list` shows the current path as a linked worktree, or the user says so): skip creation — work here.

**Otherwise:** create one:

```
EnterWorktree(name="feat/{KEY}-work")
```

Branch naming: `feat/{KEY}-work` — this exact shape, because the Lead's integration step merges `feat/{TICKET}-work` branches. If the Lead's brief names a different branch, that takes precedence.

Do **not** transition the ticket — the Lead owns ticket state.

---

## Step 3: Implement phases

Read the plan completely. Run phases in the order the plan defines them.

**Parallel phases:** if `parallel_groups` declares a group and all phases in the group are within scope (`--phases` filter), dispatch them concurrently with one `Agent()` call per phase in a single message:

```python
Agent(
    subagent_type="general-purpose",
    model="sonnet",
    run_in_background=True,
    description="Implement Phase {N} of {KEY}",
    prompt=<self-contained brief: plan path, phase number, Goal + Files + Approach verbatim,
             repo root, branch name, conventions file.
             Instruction: implement, commit `{KEY}: phase {N} — {description}`, push.
             Instruction: test discipline is `{test_discipline}` — tdd: failing test
             before code at each seam; tests-after: tests in the same change, after the
             code; off: no new tests unless the plan asks. Good-test rules apply at every
             level (inline the anti-pattern list from references/test-discipline.md —
             the sub-agent cannot load references).
             Return a ≤150-token report: what changed, any deferrals, blockers.
             Do NOT open a PR or run CI.>,
)
```

**Serial phases:** implement inline.

**Per-phase checklist (both modes):**

1. Follow project conventions; apply the configured test discipline (`test_discipline` from `.weside/config.json`, default `tests-after` — level semantics + good-test rules: `${CLAUDE_PLUGIN_ROOT}/references/test-discipline.md`)
2. Wiring check — if the phase introduces new data fields, verify they flow end-to-end
3. Security check — if touching auth/external APIs/user data: auth on new endpoints, no hardcoded secrets, parameterized queries
4. Run auto-fix for the detected stack: `ruff check --fix` / `eslint --fix` / `gofmt` / `rustfmt`
5. Commit: `{KEY}: phase {N} — {description}`

**Model tier (when dispatching subagents):** default `sonnet`; mechanical/boilerplate phases → `haiku`; explicitly hard chunks → `opus`. The Lead's model choice (if specified in the brief) takes precedence.

---

## Step 4: Local quality gates

After all phases complete, run gates in parallel for the **touched stack(s)**:

```python
Agent(subagent_type="we:static-analyzer", ...)  # lint + format + types
Agent(subagent_type="we:test-runner", ...)       # fast/unit tests only (see below)
```

**Fast-tests-only rule:** run unit tests and fast smoke tests. Skip any test that requires an
external service (running database, message queue, HTTP endpoint, Docker Compose). The
discriminator: if the test needs `DATABASE_URL`, `REDIS_URL`, `docker-compose up`, or similar —
it is an integration test and belongs to the integration CI the Lead runs after merging all
workers. Mark skipped integration tests in your Step 7 report so the Lead knows what CI will
cover.

Test quality is gated regardless of when tests were written — the anti-patterns in
[`${CLAUDE_PLUGIN_ROOT}/references/test-discipline.md`](../../references/test-discipline.md)
(implementation-coupled, tautological, horizontal slicing) fail review even under
`test_discipline: off`.

Gate failures: fix inline, commit fix, re-run. Circuit breaker: 3 failures in the same gate → stop, report to the Lead.

**Do NOT run `/we:review` here** — review is the Lead's step or happens cross-engine (Step 5).

---

## Step 5: Cross-review (when review.cross is on)

Read `review.cross` from `.weside/config.json`. Default: `true`.

**Only when `review.cross` is true:**

Determine who wrote this chunk (this session / this worker), then run the **other** engine's review
on the diff — the writer→reviewer matrix is in
[`${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md`](../../references/worker-dispatch.md) § Cross-review rule
(Claude wrote → `/codex:adversarial-review` if `tools.codex: true`, else skip with a note;
Codex/foreign wrote → local `we:code-reviewer` agent).

Cross-review runs against **this worker's diff** (not the full branch). It is informational — the worker commits even with findings. Findings go into the Step 7 report so the Lead decides whether to fix before integration.

**When `review.cross` is false or no second engine is available:** skip; note it in the report.

---

## Step 6: Commit and push

Ensure all phase commits are in. If cross-review produced obvious quick-fix findings the worker can own, fix and commit them now (`{KEY}: cross-review fixes`).

Push the branch:

```bash
git push origin {branch-name}
```

---

## Step 7: Report to the Lead

Print a structured report (≤300 tokens). When dispatched by `/we:orchestrate`, this becomes the worker's `SendMessage`:

```
Worker: develop-{KEY} [phases: {N-M or "all"}]
Branch: {branch-name}
Commits: {N commits} — {brief description of what changed}

Local gates: lint ✓ | types ✓ | tests ✓   (or: tests ✗ 2 failures — fixed)

Cross-review ({engine}): {clean | N findings — {high-level summary}}
  [list findings if any, one line each]

Blockers: {none | description}
Deferrals: {none | what was deferred and why}

Next: Lead integrates this branch. Do NOT open a PR.
```

---

## Rules

+ **Stop after push.** No PR, no per-worker CI loop, no ticket transition.
+ **Commit every phase** — atomic commits, one per phase or fix.
+ **Local gates must be green before pushing** — no gate-red push.
+ **Cross-review is informational** — commit even with findings; surface them in the report.
+ **Never dispatch to a nested /we:build** — you ARE the dev worker; calling /we:build from here is double-overhead.
+ **Honor `--phases` scope** — only implement the listed phases; do not expand scope.
+ **Report even on failure** — if a blocker stops you, report what you completed and why you stopped.
+ **Model tier defaults:** sonnet for normal phases, haiku for mechanical, opus only when the Lead explicitly requests it for a hard chunk.

## References

+ [`${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md`](../../references/worker-dispatch.md) — full dispatch contract, cross-review rule, integration-branch pattern
+ [`${CLAUDE_PLUGIN_ROOT}/references/codex-dispatch.md`](../../references/codex-dispatch.md) — Codex single-detach rule (if cross-reviewing with Codex)
+ `/we:orchestrate` — the Lead that dispatches this worker
+ `/we:build` — the solo full-pipeline alternative (PR + CI included)
