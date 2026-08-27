# Round 1 — Scenario A: Mode-B worker, --phases 2, critical money chunk

Table-top. Nothing executed. I am `worker-PAY-412-p2`, spawned by the Lead, running
`Skill(skill="develop")` for PAY-412 `--phases 2`.

## Trace

### T0 — Skill invocation

The brief says `Run: Skill(skill="develop") for PAY-412 --phases 2`. I load
`we/skills/develop/SKILL.md`.

**First decision, before Step 0, and the skill does not help with it:** the brief and the
skill disagree in three places (integration tests, AC-check, commit trailer — see defects
1/3/5). Nothing in `develop/SKILL.md` states whether the Lead's brief outranks the skill
text or the reverse. I adopt "brief wins where it is more specific" as a *guess* and carry
it through the whole run. Every fork below inherits it.

### Step 0 — Locate the plan

```
Bash: cd /home/dev/acme-PAY-412-p2 && cat docs/plans/PAY-412-story.md
```

Priority order resolves at rule 2 (ticket key) → `docs/plans/PAY-412-story.md`. Exists.
Frontmatter: `parallel_groups: [[2, 3]]`, `status: approved`. Four `### Phase` headers
present → the "at least one `### Phase` header" check passes.

`--phases 2` → scope is Phase 2 only. Files: `src/billing/refunds.py`,
`src/billing/keys.py`, `tests/unit/test_refunds.py`,
`tests/integration/billing/test_refund_idempotency.py`.

Skill line 37–40: *"When a ticket key is known, also fetch the ticket including its
comments … newest statement wins on conflict and you name the conflict to the user"*.
A ticketing tool is available.

```
ToolSearch(query="select:mcp__atlassian__jira_get_issue")
mcp__atlassian__jira_get_issue(issue_key="PAY-412", comment_limit=20)
```

**The conflict fires.** Newest comment (yesterday): *"scope cut: no partial refunds in
this story — full refunds only"*. Phase 2's Approach in the plan still describes partial
refunds. Per `ticketing.md` the newest statement wins → I build **full refunds only**.

**Where I had to invent a step.** The skill says "name the conflict *to the user*". There
is no user. My only outbound channel is EXACTLY ONE `SendMessage` to `team-lead` at the
end. So "naming it" can only mean a line in `WORKER-REPORT.md` plus a clause in the
SendMessage — which the skill never says. Worse: `orchestrate/SKILL.md` Step 3 signal 5
says a refined story whose comments contradict the plan **goes back to the refine lane,
not to a worker**. Under the Lead's own rules I am not supposed to be holding this. The
develop skill gives me no "stop and hand back" branch for it. **Decision I land on:**
implement the narrowed scope (full refunds only), do *not* stop the run, and surface the
plan-vs-ticket divergence as a question in the report. Guess, not derivation.

### Step 1 — DoR-lite

`dor-scan.md`, three items, read against the plan body: GWT ACs — 4 present ✓; `## Context`
200 words > 50 chars ✓; `^### Phase [0-9]+:` — four ✓. Pass.

This scan could not have failed. The plan is `status: approved`, written by the Lead's
refine lane and already scanned by the Lead (`refined` checkpoint, orchestrate Step 2). It
checks the three things that cannot be wrong here and is structurally blind to the one
thing that *is* wrong — the ticket comment that overtook the plan. Its failure action
("stop and say which", "point to `/we:story {TICKET}`") again addresses a user I do not
have.

### Step 2 — Worktree + branch

Brief names the worktree → skill line 54 says `cd` there and skip creation. No
`EnterWorktree`.

```
Bash: cd /home/dev/acme-PAY-412-p2 && git rev-parse --show-toplevel && git branch --show-current
```
Expect `/home/dev/acme-PAY-412-p2` / `feat/PAY-412-p2`. Branch naming rule
(`feat/{KEY}-p{N}`) matches what the Lead already made — nothing to do.

Skill line 64: *"Run the repo's worktree bootstrap from the brief (or `.weside/orchestrate.md`)
before any gate."* The brief says "already bootstrapped"; `.weside/orchestrate.md` does not
exist. So: no bootstrap command anywhere. I take "already bootstrapped" at face value and
note that `node_modules` is absent under `client/` — nothing in develop tells me that is
expected or what to do about it (that rule lives only in `codex-dispatch.md`, which develop
does not list as required reading).

No ticket transition. ✓ (I would not have done one anyway.)

### Step 3 — Implement Phase 2

```
Bash: cd /home/dev/acme-PAY-412-p2 && cat src/billing/refunds.py src/billing/keys.py
Bash: cd /home/dev/acme-PAY-412-p2 && cat tests/unit/test_refunds.py
Bash: cd /home/dev/acme-PAY-412-p2 && cat .weside/config.json
```
`config.json` = `{"test_discipline": "tests-after", "review": {"cross": false}}`.

**Parallel-phase branch:** `parallel_groups` declares `[2, 3]`, but Phase 3 is outside my
`--phases` filter, so the "all phases in the group are within scope" condition is false →
**serial, implement inline**. No `Agent()` dispatch. The whole ~20-line `Agent(...)` block
and the model-tier paragraph are dead text for me.

What the skill does *not* warn me about: Phase 3 is grouped with Phase 2 precisely because
the Lead may be running it **concurrently in another worktree**, and `keys.py` is the kind
of shared seam a sibling chunk touches. Nothing in develop tells me to check whether a
sibling chunk shares my files, or what to do if it does. I proceed and flag it.

Per-phase checklist:

1. **Test discipline** `tests-after` → code first, tests in the same change. Good-test rules
   from `test-discipline.md`: no implementation-coupled tests (do not assert
   `stripe.Refund.create` was called with an idempotency key — assert the observable:
   two identical refund requests yield one refund), no tautological assertion (the expected
   key is a literal, not recomputed by calling `build_key` the way the code does), mock at
   the Stripe boundary only.
   ```
   Edit: src/billing/refunds.py     # pass idempotency key on the refund call, full refunds only
   Edit: src/billing/keys.py        # key builder
   Edit: tests/unit/test_refunds.py # behaviour through the seam
   Write/Edit: tests/integration/billing/test_refund_idempotency.py
   ```
2. **Wiring check** — the idempotency key is a new field on the Stripe call path; I trace it
   from the refund request to the SDK call.
3. **Security check** — money + external API. No hardcoded secrets, no key derived from
   user-controlled input alone.
4. **Auto-fix** — `Bash: cd /home/dev/acme-PAY-412-p2 && ruff check --fix src tests && ruff format src tests`
   (stack detected as Python from `pyproject.toml`; `client/` untouched by this phase).
5. **Commit** — `Bash: … git add src/billing tests/unit tests/integration && git commit -m "PAY-412: phase 2 — refund idempotency key"`

**Fork A — the pre-existing currency bug.** `keys.py` builds the idempotency key without
currency, so two same-amount refunds in different currencies collide. ~20 min, on the exact
seam I am touching. The skill's Rules bullet (line 200) says **both** things in one
sentence: *"a small finding (≤ ~30 min) on the seam your phase touches gets fixed in the
same commit, not reported away. Only product decisions, **money-path changes**, and
foreign-subsystem redesigns go into the report as questions"*. This finding is ≤30 min AND
on my seam AND unambiguously on the money path. The bullet contradicts itself for exactly
this case and offers no tiebreak. **Decision:** I fix it (a colliding idempotency key on a
refund path is a correctness defect I would be shipping *around*), in a separate commit
`PAY-412: fix idempotency key collision across currencies` with a regression test, **and**
I put the fix plus my rationale in the report as a Lead question so the Lead can revert it
at integration. Guess, not derivation.

**Fork B — the integration test I am told to write and forbidden to run.** Phase 2's
`**Files:**` includes `tests/integration/billing/test_refund_idempotency.py`. Step 4 says
skip anything needing `DATABASE_URL`. So under the skill alone I would author a test I am
forbidden to execute — an unverified artifact shipped as done. The brief rescues this; the
skill does not.

**Commit trailer.** `orchestrate/SKILL.md` Rules: *"Every worker commit carries
`Co-Authored-By: <Engine> <Model> <noreply@…>`"*. `develop/SKILL.md` Step 3 item 5 gives the
commit format with no trailer. I add
`Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` from the Lead's rule, guessing the
exact string.

### Step 4 — Local quality gates

Skill: two agents, in parallel, arguments literally elided as `...`. I invent both prompts.

```python
Agent(subagent_type="we:static-analyzer",
      description="Static gates PAY-412 p2",
      prompt="cwd /home/dev/acme-PAY-412-p2. Python only — ruff check + ruff format --check "
             "over src/ and tests/. Do NOT run node/tsc/eslint: client/ has no node_modules "
             "in this worktree and installing is forbidden by the brief. Report pass/fail.")
Agent(subagent_type="we:test-runner",
      description="Fast tests PAY-412 p2",
      prompt="cwd /home/dev/acme-PAY-412-p2. Run `pytest tests/unit -q` only. Do NOT run "
             "tests/integration — it needs a database. Report pass/fail + failures.")
```
Everything after "Python only" I made up: the skill's Step 4 never says how to tell either
agent the fast-tests-only rule or the no-`node_modules` rule.

**Then the conflict that matters.** Step 4 lines 118–123 are unconditional: *"Skip any test
that requires an external service (running database …). The discriminator: if the test needs
`DATABASE_URL` … it is an integration test and belongs to the integration CI the Lead
runs."* My brief says the opposite, because this is a CRITICAL money chunk:
*"run `pytest tests/integration/billing -q` against `acme_test` before reporting done — this
chunk is never fast-gates-only."* `develop/SKILL.md` has **no** critical-chunk exception
anywhere. Postgres is up and reachable.

**Decision:** brief wins — I run it.
```
Bash: cd /home/dev/acme-PAY-412-p2 && DATABASE_URL=postgresql://…/acme_test \
      pytest tests/integration/billing -q > /tmp/pay412-p2-int.txt 2>&1; tail -20 /tmp/pay412-p2-int.txt
```
A worker following the skill alone ships a money chunk that never touched Postgres.

Gate failures → fix inline, commit, re-run; circuit breaker at 3. Understood, no ambiguity.

Line 132's *"Do NOT run `/we:ac-review` standalone here — this step runs the same agent
inline"* is wrong on its face: Step 4 dispatches `we:static-analyzer` and `we:test-runner`,
neither of which is `we:ac-reviewer`. The AC agent runs in Step 5, not here.

### Step 5 — AC-check

```
Bash: cd /home/dev/acme-PAY-412-p2 && cat .weside/config.json
```
`review.cross` is **false** → skill line 155: *"skip the AC-check; note it in the report."*
But my brief's DEV-ONLY line says `AC-check your diff` with no condition, and orchestrate's
Worker-Brief template hardcodes it for every worker regardless of config.

**Decision:** I run it, because the brief is the more specific instruction and this is a
money chunk where the AC/DoD read is cheap.
```python
Agent(subagent_type="we:ac-reviewer",
      description="AC-check PAY-412 p2 diff",
      prompt="Diff: `git -C /home/dev/acme-PAY-412-p2 diff feat/PAY-412-integration...HEAD`. "
             "Check it against the ACs in docs/plans/PAY-412-story.md that Phase 2 claims, "
             "narrowed by the ticket's newest comment: full refunds only, no partial refunds. "
             "Informational — report findings, do not gate.")
```
Flagged as a guess. Which of brief and config wins is not written anywhere. Note also that
line 139 says the *default* is `true` while a repo that explicitly wrote `false` presumably
meant it — the skill gives the flag a default and then no override rule.

### Step 6 — Commit and push

AC-check quick-fixes, if any, commit as `PAY-412: AC-check fixes`.

```
Bash: cd /home/dev/acme-PAY-412-p2 && git status --porcelain && git log --oneline feat/PAY-412-integration..HEAD
Bash: cd /home/dev/acme-PAY-412-p2 && git push origin feat/PAY-412-p2
Bash: cd /home/dev/acme-PAY-412-p2 && git rev-parse HEAD origin/feat/PAY-412-p2   # invented
```
The last call is mine. The skill gives one bare `git push origin {branch-name}` with no
`-u`, no rejected-push handling, and no verification — while the brief says *"NEVER report
done without a pushed branch."* The check that discharges that sentence does not exist in
the skill.

**Generated artifacts.** Brief: regenerate and commit `openapi.json` if endpoints changed.
Phase 2 touches `refunds.py` / `keys.py` with no endpoint or response-model change
described, so nothing to regenerate — it did not bite here. But `develop/SKILL.md` has no
generated-artifact step at all; the rule lives only in `codex-dispatch.md`, which develop
does not tell me to read. `.coverage-baseline` is Lead-owned — I confirm it is untouched
(`git status --porcelain` shows it absent), a check the skill never asks for.

### Step 7 — Report

Two report shapes, and I reconcile them by hand:

- **The skill** (lines 173–189): "Print a structured report (≤300 tokens)", fields
  `Worker/Branch/Commits/Local gates/AC-check/Blockers/Deferrals/Next`. Printed output is
  invisible to the Lead — the skill half-acknowledges this (*"When dispatched by
  `/we:orchestrate`, this becomes the worker's `SendMessage`"*) but gives no `to=`, no
  `summary=`, and no statement that plain text does not reach anyone.
- **The brief**: `WORKER-REPORT.md` in the worktree root, not `git add`ed, plus EXACTLY ONE
  `SendMessage(to="team-lead", …)` with fields `branch | commits | gates | AC-check |
  skipped | blockers`.

`WORKER-REPORT.md` appears **zero times** in `develop/SKILL.md`. A worker on the skill alone
never writes it.

```
Write: /home/dev/acme-PAY-412-p2/WORKER-REPORT.md
```
containing: full-refunds-only scope narrowing from the ticket comment vs. the plan's
partial-refund Approach (question for the Lead); the currency-collision fix and why I
took it despite the money-path clause; the last 20 lines of the integration run; frontend
validation skipped (no `node_modules`); `.coverage-baseline` untouched; the Phase-3
shared-`keys.py` collision risk.

```
ToolSearch(query="select:SendMessage")
SendMessage(to="team-lead", summary="worker-PAY-412 done",
  message="feat/PAY-412-p2 | commits: 3 | gates: lint ✓ types n/a (py) tests ✓ (unit) + "
          "integration/billing ✓ vs acme_test | AC-check: run despite review.cross:false, "
          "N findings | skipped: client/ jest+tsc (no node_modules) | blockers: none | "
          "QUESTIONS: (1) ticket comment cuts partial refunds, plan Phase 2 Approach still "
          "describes them — built full-refunds-only, plan needs a rewrite; (2) fixed a "
          "pre-existing currency-blind idempotency key in keys.py (money path — revert at "
          "integration if you want it separate); (3) keys.py is shared with Phase 3.")
```
Stop. No PR, no CI, no ticket transition.

## Conformance checklist

| Contract (brief + skill) | Met? | Why |
|---|---|---|
| Implement phase 2 only, no scope expansion | ✓ | Step 0 `--phases` filter + Rules line 200 are clear |
| Read the ticket **with comments**, honour the newest statement | ✓ | Step 0 lines 37–40 sent me there |
| Handle a plan-vs-ticket conflict correctly | ✗ | Skill says "name it to the user"; no user exists, no worker branch, and orchestrate says this case belongs in the refine lane, not with me |
| `parallel_groups` handled | ✓ | Group not fully in scope → serial inline. Correct by the letter |
| Avoid clobbering a concurrent sibling chunk on shared `keys.py` | ✗ | Skill never mentions sibling-chunk file overlap |
| Test discipline `tests-after` + good-test rules | ✓ | Step 3 item 1 + `test-discipline.md` are solid |
| Fast gates only | ✓ | Step 4 is explicit |
| CRITICAL money chunk runs the integration suite | ✗ | Step 4 forbids it unconditionally; only the brief saves it |
| Author the plan's integration test I may not run | ✗ | Write-but-don't-run is unaddressed |
| Append the integration run's last 20 lines to the report file | ✗ | Skill has no report file and no evidence field |
| AC-check the diff | ✗ | Skill skips it on `review.cross: false`; brief demands it; no precedence rule |
| Finish-first on the currency bug | ✗ | One bullet says fix it and says money-path → question; no tiebreak |
| `Co-Authored-By` trailer on every worker commit | ✗ | Orchestrate requires it; develop's commit format omits it |
| Regenerate generated artifacts if needed | ✗ (didn't bite) | No generated-artifact step in develop at all |
| Don't touch `.coverage-baseline` | ✓ | Trivially — brief said so; skill silent |
| Push, and never report done without a pushed branch | ✗ | Bare `git push`, no verification step |
| Write `WORKER-REPORT.md` | ✗ | Zero mentions in the skill |
| Send exactly one `SendMessage` to `team-lead` | ✗ | Named once, no call shape, fields don't match the brief's |
| Stop after push — no PR/CI/ticket | ✓ | Stated four times, unmissable |

## Skill defects

**1. `[MISSING MECHANIC]` — no precedence rule between the Lead's brief and the skill.**
Nothing in `develop/SKILL.md` says which wins. The nearest thing is two local overrides —
line 54 *"If the Lead's brief names a worktree path"* and line 62 *"A branch named in the
Lead's brief takes precedence"*, line 105 *"The Lead's model choice (if specified in the
brief) takes precedence"* — three narrow carve-outs that, by naming themselves, imply the
brief does **not** outrank the skill elsewhere. This one absence is the root of defects
2, 5 and 7. *Fix:* one line at the top — "the Lead's brief outranks any default in this
skill; a brief that contradicts a step is the step's override, and you name it in the report."

**2. `[MISSING MECHANIC]` — no critical/money-chunk exception to the fast-gates rule.**
Lines 118–122: *"Skip any test that requires an external service (running database, message
queue, HTTP endpoint, Docker Compose). The discriminator: if the test needs `DATABASE_URL`
… it is an integration test and belongs to the integration CI the Lead runs."* Orchestrate
Step 5.2 classifies money chunks as *"never fast-gates-only (the brief names the integration
suite and the database)"*, and my brief does exactly that — but develop contradicts it flatly
and a worker reading only the skill ships an untested money path. *Fix:* add "unless the
brief names an integration suite and a database — a critical chunk runs it and appends the
last 20 lines to the report."

**3. `[MISSING MECHANIC]` — `WORKER-REPORT.md` does not exist in this skill.** Step 7 says
only *"Print a structured report (≤300 tokens)"*. The file is mandated by the brief, by
`codex-dispatch.md` (*"Make the outcome an artifact, because the report has no
recipient"*) and by orchestrate Step 7's evidence ladder — and appears nowhere in develop.
A worker on the skill alone leaves the Lead nothing to read. *Fix:* Step 7 writes
`WORKER-REPORT.md` (not `git add`ed), with a named field for critical-gate evidence.

**4. `[MISSING MECHANIC]` — the worker has no channel for a plan-vs-ticket conflict.**
Lines 38–40: *"newest statement wins on conflict and you name the conflict **to the user**"*
— and Step 1's failure action, *"stop and tell the user"*. There is no user in a dispatched
worker; there is one `SendMessage` and a report file. Meanwhile orchestrate Step 3 signal 5
says a refined story the comments have overtaken *"goes back to the refine lane, not to a
worker"* — so the skill should give me a stop-and-hand-back branch and instead tells me to
apply "newest wins" and build on. In this scenario I silently narrowed the story's scope
(no partial refunds) on my own authority. *Fix:* replace "the user" with "the Lead (report
file + your one message)" everywhere, and add: a scope-changing comment stops the chunk.

**5. `[CLARITY]` — `review.cross: false` vs. a brief that orders the AC-check.** Line 139
*"Read `review.cross` from `.weside/config.json`. Default: `true`"* and line 155 *"When
`review.cross` is false: skip the AC-check"*, against a brief whose DEV-ONLY line says
`AC-check your diff` unconditionally — and orchestrate's Worker-Brief template hardcodes it
for every worker regardless of the flag. Both artifacts ship in the same plugin. *Fix:*
either the template reads the flag, or develop says the brief's explicit AC-check overrides
`review.cross: false`.

**6. `[CLARITY]` — the finish-first bullet contradicts itself on a money-path seam finding.**
Line 200: *"a small finding (≤ ~30 min) on the seam your phase touches gets fixed in the
same commit, not reported away. Only product decisions, money-path changes, and
foreign-subsystem redesigns go into the report as questions"*. A currency-blind idempotency
key is ≤30 min, on my seam, and on the money path — all three at once, in the same sentence,
with no tiebreak. *Fix:* rank them — "money-path findings are fixed in a separate commit and
reported as a question, so the Lead can revert them at integration."

**7. `[MISSING MECHANIC]` — no `Co-Authored-By` trailer in the commit format.** Step 3 item
5: *"Commit: `{KEY}: phase {N} — {description}`"*, while orchestrate's Rules demand
*"Every worker commit carries `Co-Authored-By: <Engine> <Model> <noreply@…>`"*. The worker,
the only one who can add it, is never told to. I invented the string. *Fix:* put the trailer
in the commit format.

**8. `[MISSING MECHANIC]` — the plan assigns an integration test the skill forbids running.**
Phase 2's `**Files:**` names `tests/integration/billing/test_refund_idempotency.py`; Step 4
line 118 forbids executing it. Write-but-never-run is not addressed anywhere, so the default
outcome is an unverified test file shipped as a deliverable. *Fix:* say it explicitly —
"author it, do not run it, and list it in the report as unverified" — or fold it into the
critical-chunk exception (defect 2).

**9. `[MISSING MECHANIC]` — Step 4's gate agents have elided arguments.** Lines 114–115:
`Agent(subagent_type="we:static-analyzer", ...)` / `Agent(subagent_type="we:test-runner",
...)`. The two rules that matter most — fast-tests-only, and no node tooling in a worktree
without `node_modules` — live in the prose (and in `codex-dispatch.md`, which develop does
not require) rather than in the prompt the agents actually receive. I wrote both prompts from
scratch. *Fix:* give both calls a real prompt string carrying the two rules.

**10. `[CLARITY]` — `SendMessage` is named but not specified.** Line 173: *"When dispatched
by `/we:orchestrate`, this becomes the worker's `SendMessage`"* — no `to=`, no `summary=`,
no "your printed output is invisible", and the template's fields (`Deferrals`, `Next:`)
do not match the brief's (`skipped:`, `blockers:`). Two report shapes for one report.
*Fix:* one shape, with the call written out.

**11. `[CLARITY]` — line 132 mis-describes its own step.** *"Do NOT run `/we:ac-review`
standalone here — this step runs the same agent inline"*. Step 4 runs `we:static-analyzer`
and `we:test-runner`; the AC agent runs in Step 5. The sentence tells me not to duplicate
something this step does not do. *Fix:* delete it, or move it into Step 5.

**12. `[MISSING MECHANIC]` — no generated-artifact step.** Nothing in develop mentions
regenerating `openapi.json`/types or leaving gate-baseline files alone; the OpenAPI trap is
documented only in `codex-dispatch.md`, which develop lists as "if the Lead uses Codex". It
did not bite in this scenario (Phase 2 changes no endpoint), but it is unguarded. *Fix:* one
line in Step 6.

**13. `[MISSING MECHANIC]` — nothing warns about a concurrent sibling chunk on a shared
file.** `parallel_groups: [[2, 3]]` means Phase 3 may be running right now, and `keys.py` is
exactly the kind of file two chunks in one group share. Step 3 reads `parallel_groups` only
to decide whether *I* fan out. *Fix:* "phases grouped with yours may be building
concurrently — treat any file also listed under them as a shared seam and say so in the
report."

**14. `[CUT]` — the parallel-`Agent()` block, the model-tier paragraph, and the duplicate
Rules bullet.** Lines 75–93 (a 19-line `Agent(...)` template), line 105 (*"Model tier (when
dispatching subagents): default `sonnet`…"*) and Rules line 202 (*"Model tier defaults:
sonnet for normal phases…"*) say the same thing twice and are unreachable for a Mode-B
worker scoped to one phase — the common case this skill exists for. A worker that *did*
fan out would be dispatching a nested pipeline the Rules forbid two lines earlier.

**15. `[CUT]` — Step 1's DoR-lite on an approved plan.** The Lead already ran this exact
scan (`refined` checkpoint) before dispatching. It checks the three things that cannot be
wrong on an approved plan and is blind to the one thing that is (defect 4). Worth keeping
only for the un-briefed standalone invocation — say so, so a dispatched worker skips it.

**16. `[CUT]` — Step 2's worktree-detection prose for a briefed worker.** *"If the Lead's
brief names a worktree path (or `git worktree list` shows the current path as a linked
worktree): `cd` there and skip creation"* — the brief already said "`cd` there; do not call
`EnterWorktree`". And *"Run the repo's worktree bootstrap from the brief (or
`.weside/orchestrate.md`)"* resolves to nothing when the brief says "already bootstrapped"
and the file does not exist — no fallback stated, which is a small `[CLARITY]` inside a
mostly-cuttable step.

## What I needed and did not find

- **Which artifact wins when the brief and the skill disagree.** Three separate collisions in
  one run, each resolved by my own guess.
- **A stop-and-hand-back branch** for a ticket comment that changes scope after the plan was
  approved. I narrowed a story's scope with no mandate to.
- **A tiebreak** between "fix small findings on your seam" and "money-path changes are
  questions".
- **The report file, and the exact `SendMessage` call.** Both are in the brief; neither is in
  the skill, so the skill alone produces a report nobody reads.
- **Evidence discipline for the critical gate** — "append the last 20 lines" exists only in
  the brief; the skill has no field for it.
- **A push-verification step** to discharge "never report done without a pushed branch".
- **Any acknowledgement that a sibling chunk in my `parallel_groups` may hold my files open.**

## Grade

**2/5.** The spine is right and unmissable: locate plan → scope by `--phases` → implement
with the configured test discipline → gates → commit → push → stop, with "no PR, no CI, no
ticket transition" repeated often enough that no worker will get that wrong. That is worth
something and it is why this is not a 1. But two of the failures are outcome-changing, not
cosmetic. A worker following **only** this skill (a) skips the integration suite on a money
chunk because Step 4 forbids it without exception, shipping an untested Stripe refund path,
and (b) prints its report into a void, because `WORKER-REPORT.md` is absent from the skill
and `SendMessage` is named without a shape — the two failure modes the Lead's own references
spend pages warning about. A third, quieter one: the skill sent me to read the ticket
comments, handed me a scope cut that contradicts an approved plan, and then had no branch for
it, so I narrowed the story myself. Everything that saved this run came from the brief, and
the skill never says the brief may do that. Meanwhile ~35 lines of subagent-dispatch and
model-tier text is unreachable for the single-phase Mode-B worker this skill mostly serves.
Not a fresh worker's instruction set yet — it is a good outline that the Lead's brief has
been quietly patching.
