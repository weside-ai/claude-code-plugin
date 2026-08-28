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

Implement the assigned chunk, run local gates, commit, push, stop. No PR, no CI fix loop, no
ticket transition — the Lead (`/we:orchestrate`) merges every worker onto one branch and runs CI
**once**; with no Lead in play, `--solo` does both.

**The Lead's brief outranks every default in this skill.** Where the brief names a worktree,
branch, test discipline, gate list or integration suite, that value wins over `.weside/config.json`
and over the steps below; you name the override in your report. The brief is silent → the step
applies. What it does not override is a **stop**: a brief says build, and the stop branches below
fire on facts the Lead did not have when it wrote one. Full dispatch contract:
[`${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md`](../../references/worker-dispatch.md)

**You are talking to the Lead, not a user.** Dispatched, your printed output is invisible: the
only channels out are `WORKER-REPORT.md` and exactly one `SendMessage` (Step 6) — invoked by a
human instead, the same content goes to the chat. **Stopping early** means all three: write the
report file with what you completed and why you stopped, send the one message with
`blocked: <reason>`, stop. A stop without a message is a chunk the Lead waits on forever.

---

## Step 0: Locate the plan

1. Explicit path argument → use as-is
2. Ticket key → `docs/plans/{KEY}-story.md` (relative to the repo root the brief names, not the
   worktree, when they differ)
3. No argument → `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story status` and pick
   the active one

**`--phases N,M`:** implement only those `### Phase` blocks. Absent → all phases.

**Standalone invocation only** (no Lead brief): run the 3-item scan from
[`${CLAUDE_PLUGIN_ROOT}/references/dor-scan.md`](../../references/dor-scan.md) and stop if it
fails, naming the item. A briefed worker skips it — the Lead ran it before dispatch.

**A plan carrying an unanswered `## Open Fork` section is not buildable** — a refiner left a
decision open there, and building past it pins behaviour nobody chose: stop and hand it back. The
section survives an answer written straight into the plan or the brief (nobody re-ran the refiner
to clear it): where the answer is there, name it in your report and build on it.

**When a ticket key is known**, fetch the ticket **including its comments**
([`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`](../../references/ticketing.md)). A comment that
only clarifies: build the newest statement and record the conflict in your report. A comment that
**changes scope** after the plan was approved (a cut, a new AC, a different seam) is not yours to
absorb — stop and hand it back as a question; re-planning is the refine lane's job. No ticketing
tool → plan file only, say so.

---

## Step 1: Worktree + branch

**Brief names a worktree** (or `git worktree list` shows the current path as a linked worktree):
`cd` there, do not call `EnterWorktree`, and run the bootstrap the brief names unless it says the
worktree is already bootstrapped. **Otherwise:** `EnterWorktree(name="feat/{KEY}-work")` —
`feat/{KEY}-p{N}` when `--phases N` scopes the chunk. A branch named in the brief wins.

Do **not** transition the ticket — the Lead owns ticket state.

---

## Step 2: Implement phases

Read the plan completely and implement its phases **in the order the plan defines them, inline**.
Never fan the *implementation* out to sub-agents (the gates in Step 3 are the exception, and they
write nothing): phases in one worktree share one git index, so two concurrent committers race
`.git/index.lock` and push the same branch. `parallel_groups` is the Lead's tool
for splitting phases across separate worker worktrees. A phase grouped with yours but outside your
`--phases` scope may be building right now: a file listed under **both** it and your phases is a
shared seam — say so in your report rather than assuming you own it.

Per phase:

1. Apply the test discipline the brief names (`.weside/config.json`'s `test_discipline` is the
   fallback, default `tests-after`) — level semantics and the anti-patterns that fail review at
   every level: [`${CLAUDE_PLUGIN_ROOT}/references/test-discipline.md`](../../references/test-discipline.md).
   A test file the discipline requires is in scope even when the plan's `**Files:**` omits it.
2. Wiring check — a new data field flows end-to-end, not just into the model.
3. Security check — touching auth, external APIs or user data: auth on new endpoints, no
   hardcoded secrets, parameterized queries.
4. Regenerate what the brief lists as a generated artifact (OpenAPI schema, typed client) and
   commit it; leave gate-baseline files (coverage ratchets, allowlists) to the Lead.
5. Stage the phase's files **by path** — never `git add -A`, which would sweep
   `WORKER-REPORT.md` into the diff. Commit:

```
{KEY}: phase {N} — {description}

Co-Authored-By: <Engine> <Model> <noreply@…>
```

Fill the trailer with the engine and model actually running you (the brief names them when it
dispatched a specific backend); the Lead never re-signs a worker's commits.

---

## Step 3: Local quality gates

Run both for the **touched stack(s)**, in one message:

```python
Agent(subagent_type="we:static-analyzer",
      prompt="Lint, format and type-check the changes on branch {branch} in {worktree}. "
             "Do not run `yarn`/`npm install`, `tsc` or `eslint` in a worktree without "
             "node_modules — report that as skipped. Report findings; fix nothing.")
Agent(subagent_type="we:test-runner",
      prompt="Run only unit and fast smoke tests for the changes on {branch} in {worktree}. "
             "SKIP any test needing DATABASE_URL, REDIS_URL, a queue, an HTTP service or "
             "docker-compose, and list what you skipped. Do not run `yarn`/`npm install`, "
             "`jest` or `tsc` in a worktree without node_modules — report that as skipped.")
```

**Fast-tests-only, with one exception:** when the brief names an integration suite and a database
for a **critical** chunk (money, auth, tenant isolation, migration), that chunk is never
fast-gates-only — run the suite and keep its last 20 lines for the report file you write in
Step 6, so the claim is checkable. Everything else needing an external service belongs to the
Lead's integration CI: an integration test the plan asks you to *write* gets written and left
unrun, listed as unverified.

Gate failures: fix inline, commit the fix, re-run. Circuit breaker: 3 failures in the same gate →
stop.

---

## Step 4: AC-check your diff

Run when the brief orders an AC-check, or — brief silent — when `review.cross` in
`.weside/config.json` is true (its default). Explicit brief beats the flag either way. Agent
teammates only: a Codex or foreign-engine worker cannot spawn `we:ac-reviewer` — skip and say so
in the report; the Lead's integration gate covers it.

```python
Agent(subagent_type="we:ac-reviewer",
      prompt="Check `git diff {integration_branch}...HEAD` against the ACs the phases "
             "you built ({the --phases scope, or all}) claim to satisfy in "
             "docs/plans/{KEY}-story.md. Findings only.")
```

The integration branch comes from the brief; standalone, use the branch you cut from. Findings are
**informational** — fix what you own, commit it (`{KEY}: AC-check fixes`), report them either way.
No separate `/we:ac-review` pass and no bug-hunt: Codex adversarial-review and `/code-review` run
exactly once, at Lead integration, over the merged diff (`references/worker-dispatch.md`
§ AC-review rule).

---

## Step 5: Push

```bash
git push -u origin {branch} && git ls-remote --heads origin {branch}
```

An empty `ls-remote` means the push did not land — that is a blocker, not a done.

---

## Step 6: Report

Write `WORKER-REPORT.md` in the worktree root — what you built, what you skipped, what you could
not settle, plus the critical-gate output if Step 3 ran one. It is not part of the change: never
`git add` it.

Then send exactly one message (`SendMessage` is a deferred tool — `ToolSearch` for it first):

```python
SendMessage(to="team-lead", summary="worker-{KEY} done|blocked",
            message="{branch} | commits: N | gates: lint ✓ types ✓ tests ✓ | "
                    "AC-check: clean|N findings | skipped: … (or none) | "
                    "questions: … | blockers: none|reason")
```

Invoked by a human instead of a Lead: print the same fields.

---

## Rules

+ **Stop after push.** No PR, no per-worker CI loop, no ticket transition, no nested pipeline —
  opening a PR or running CI here voids the Lead's single-CI contract.
+ **Local gates green before pushing** — no gate-red push.
+ **Honor `--phases` scope.** Expanding scope means NEW capability, not deferred defects: a
  finding ≤ ~30 min on the seam your phase touches gets fixed here. A **money-path** finding is
  the exception — fix it in its own commit *and* raise it as a question, so the Lead can revert it
  at integration. Product decisions and foreign-subsystem redesigns are questions only; workers
  never create tickets.
+ **Report even on failure** — what you completed, why you stopped.

## References

+ [`${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md`](../../references/worker-dispatch.md) — dispatch contract, AC-review rule, model tiers
+ [`${CLAUDE_PLUGIN_ROOT}/references/integration-pipeline.md`](../../references/integration-pipeline.md) — what the Lead does with your branch
+ [`${CLAUDE_PLUGIN_ROOT}/references/codex-dispatch.md`](../../references/codex-dispatch.md) · `/we:orchestrate` — the Codex single-detach rule, and the Lead that dispatches you
