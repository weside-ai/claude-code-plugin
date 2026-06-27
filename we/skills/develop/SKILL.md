---
name: develop
description: >
  Dev-only worker slice — implements the assigned chunk (Story or phase subset),
  runs local quality gates (lint/type/test for the touched stack), commits, pushes
  its branch, and STOPS. No PR, no CI loop, no ticket transition. The Lead
  (/we:orchestrate) integrates and runs CI once. Cross-reviews its own diff when
  review.cross is on. Returns a short structured report.
  Use when the user says "/we:develop", "implement only", "dev worker", "no PR",
  "just implement and push", or when /we:orchestrate dispatches a chunk.
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

Quick scan — three items only. If any fail, stop and say which:

1. At least one GWT acceptance criterion (`Given` + `When` + `Then`)
2. Context section present and non-empty (> 50 chars)
3. At least one `### Phase \d+:` header

This is lighter than `/we:build`'s full DoR gate — the goal is to catch a completely un-refined plan, not to be a final gate.

---

## Step 2: Worktree + branch

**If already in a dedicated worktree** (detected by: `git worktree list` shows the current path as a linked worktree, or the user says so): skip creation — work here.

**Otherwise:** create one:

```
EnterWorktree(name="{type}/{KEY}-develop")
```

Branch naming: `{type}/{KEY}-<short-description>` (e.g. `feat/PROJ-31-engine-profiles`).

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
             Instruction: follow TDD — test first, then implementation.
             Return a ≤150-token report: what changed, any deferrals, blockers.
             Do NOT open a PR or run CI.>,
)
```

**Serial phases:** implement inline.

**Per-phase checklist (both modes):**

1. Follow project conventions; TDD (test first, then implementation)
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

Gate failures: fix inline, commit fix, re-run. Circuit breaker: 3 failures in the same gate → stop, report to the Lead.

**Do NOT run `/we:review` here** — review is the Lead's step or happens cross-engine (Step 5).

---

## Step 5: Cross-review (when review.cross is on)

Read `review.cross` from `.weside/config.json`. Default: `true`.

**Only when `review.cross` is true:**

Determine who wrote this chunk (this session / this worker). Then run the **other** engine's review on the diff:

| This worker | Cross-reviewer |
|---|---|
| Claude (any tier) | `/codex:adversarial-review` — only when `tools.codex: true`; if Codex absent, skip with one-line note |
| Codex | local `code-reviewer` agent |
| Foreign engine | local `code-reviewer` agent |

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
