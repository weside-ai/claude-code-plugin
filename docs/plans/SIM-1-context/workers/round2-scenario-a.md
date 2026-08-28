# Round 2 — Scenario A: Mode-B worker, --phases 2, critical money chunk

Table-top. Nothing executed. I am `worker-PAY-412-p2`, spawned by the Lead, running
`Skill(skill="develop")` for PAY-412 `--phases 2`, against the **revised**
`we/skills/develop/SKILL.md`.

## Trace (revised skill)

### T0 — Invocation, and the question round 1 had to guess

I load the skill. Before Step 0 the file answers the question that was round 1's root defect:

> line 19: "**The Lead's brief outranks every default in this skill.** Where the brief names a
> worktree, branch, test discipline, gate list or integration suite, that value wins over
> `.weside/config.json` and over the steps below; you name the override in your report. The brief
> is silent → the step applies."

and the channel question:

> line 25: "**You are talking to the Lead, not a user.** Dispatched, your printed output is
> invisible: the only channels out are `WORKER-REPORT.md` and exactly one `SendMessage` (Step 6)."

and the early-stop protocol:

> line 29: "**Stopping early** — at any stop below, do all three: write `WORKER-REPORT.md` with what
> you completed and why you stopped, send the one message with `blocked: <reason>`, stop."

Three guesses from round 1 are gone before I read a step.

### Step 0 — Locate the plan

```
Bash: cd /home/dev/acme-PAY-412-p2 && cat docs/plans/PAY-412-story.md
```

Rule 2 (ticket key) → `docs/plans/PAY-412-story.md`. Exists, `status: approved`,
`parallel_groups: [[2, 3]]`, four `### Phase` blocks. `--phases 2` → Phase 2 only:
`src/billing/refunds.py`, `src/billing/keys.py`, `tests/unit/test_refunds.py`,
`tests/integration/billing/test_refund_idempotency.py`.

DoR-lite: not mine.

> line 45: "**Standalone invocation only** (no Lead brief): run the 3-item scan … A briefed worker
> skips it — the Lead ran it before dispatch."

I have a brief. Skipped. (Round-1 defect 15 was exactly this.)

Ticket read:

```
ToolSearch(query="select:mcp__atlassian__jira_get_issue")
mcp__atlassian__jira_get_issue(issue_key="PAY-412", comment_limit=20)
```

Newest comment (yesterday): *"scope cut: no partial refunds in this story — full refunds only"*.
The plan's Phase 2 Approach still describes partial refunds.

> line 50: "A comment that only clarifies: build the newest statement and record the conflict in
> your report. A comment that **changes scope** after the plan was approved (a cut, a new AC, a
> different seam) is not yours to absorb — stop and hand it back as a question; re-planning is the
> refine lane's job."

The comment says "scope cut" in its own words. This is the second branch. **The run stops here.**
Round 1 narrowed a story's scope on its own authority; the revised skill routes it to the refine
lane, matching `orchestrate/SKILL.md` Step 3 signal 5 ("a refined story with this signal goes back
to the refine lane, not to a worker"). That is the correct outcome, and it is now derived, not
invented.

**The hesitation, and it is not small.** Line 19 says the brief outranks *every default in this
skill*, and my brief is an unconditional order to build: "implement phase 2 → fast local gates →
AC-check your diff → commit → push". A worker can read the dispatch itself as the brief having
spoken on whether to build, which makes the Step-0 stop a "default" the brief outranks. Nothing
says a stop branch is exempt. I resolve it toward the stop — line 22's "The brief is silent → the
step applies" plus the fact that the brief never mentions the comment — but this is the one place
left where a fresh worker could go either way, on the run's most consequential decision. See new
defect **N1**.

Per line 29 I do all three:

```
Write: /home/dev/acme-PAY-412-p2/WORKER-REPORT.md
```
containing: the scope-cut comment vs. the plan's partial-refund Approach; that Phase 2 is
unimplemented; that `keys.py` carries a pre-existing currency-blind idempotency key I found while
reading and did not touch; that Phase 3 shares `keys.py` with me under `parallel_groups`; that the
critical integration gate never ran because nothing was built.

```python
ToolSearch(query="select:SendMessage")
SendMessage(to="team-lead", summary="worker-PAY-412 blocked",
            message="feat/PAY-412-p2 | commits: 0 | gates: not run | AC-check: not run | "
                    "skipped: everything | questions: ticket's newest comment cuts partial "
                    "refunds, plan Phase 2 Approach still specifies them — scope change, refine "
                    "lane per Step 0 | blockers: plan-vs-ticket scope conflict")
```
Stop. No PR, no CI, no ticket transition, no push (nothing to push — and Step 5's `ls-remote`
check would have caught a phantom push).

### Counterfactual continuation

The stop makes Steps 1–6 unreachable in this scenario, and with them the money-gate mechanic that
round-1 defect 2 asked for. To re-judge defects 2, 6, 7, 8, 9, 12 and 13 I continue the trace
**under the counterfactual that the comment had only clarified** (so line 50's first branch
applies: build the newest statement, record the conflict in the report).

### Step 1 — Worktree + branch (counterfactual)

> line 60: "**Brief names a worktree path** … `cd` there, do not call `EnterWorktree`. Run the
> bootstrap the brief names, unless it says the worktree is already bootstrapped."

The brief says "already bootstrapped" → nothing to run. Round 1's dangling case (brief says
bootstrapped, `.weside/orchestrate.md` absent, no fallback stated) is now explicitly resolved.
`git rev-parse --show-toplevel` + `git branch --show-current` per the brief. No ticket transition
(line 67).

### Step 2 — Implement (counterfactual)

> line 74: "Never fan out to sub-agents: phases in one worktree share one git index … a phase
> grouped with yours may be building right now, so treat any file listed under it as a shared seam
> and say so in your report."

Two round-1 defects die in one paragraph: the dead ~19-line `Agent(...)` fan-out template (14) and
the missing sibling-chunk warning (13). `keys.py` is under Phase 3 → shared seam → report line.

Per-phase checklist: test discipline from the brief (`tests-after`; `.weside/config.json` agrees) →
code first, tests same change, `test-discipline.md` anti-patterns (no assertion that
`stripe.Refund.create` received an idempotency key; expected key a literal, not recomputed; mock at
the Stripe boundary only). Item 1's "A test file the discipline requires is in scope even when the
plan's `**Files:**` omits it" is new and correct. Wiring check, security check.

> line 88: "Regenerate what the brief lists as a generated artifact (OpenAPI schema, typed client)
> and commit it; leave gate-baseline files (coverage ratchets, allowlists) to the Lead."

Covers both halves of the brief's REPO CONSTRAINTS in one line — `openapi.json` (no endpoint
change here, so nothing) and `.coverage-baseline` (Lead's). Round-1 defect 12 gone.

> line 90: "Stage the phase's files **by path** — never `git add -A`, which would sweep
> `WORKER-REPORT.md` into the diff."

Commit block now carries `Co-Authored-By: <Engine> <Model> <noreply@…>` (line 96). Round-1 defect 7
gone; I still resolve the placeholders myself (`Claude Opus 5 <noreply@anthropic.com>`), which is
the same latitude `orchestrate/SKILL.md` line 524 gives.

**The currency bug.** Rules, line 182:

> "a finding ≤ ~30 min on the seam your phase touches gets fixed here. The exception is a
> **money-path** finding — fix it in its own commit *and* raise it as a question, so the Lead can
> revert it at integration."

Derived, not guessed: separate commit + report question. Round 1 had to invent exactly this
resolution.

### Step 3 — Gates (counterfactual)

Both agents now carry real prompts. The `we:test-runner` prompt carries both rules that matter:

> line 110: "Run only unit and fast smoke tests … SKIP any test needing DATABASE_URL, REDIS_URL, a
> queue, an HTTP service or docker-compose, and list what you skipped. Do not run `yarn`/`npm
> install`, `jest` or `tsc` in a worktree without node_modules — report that as skipped."

The `we:static-analyzer` prompt carries neither:

> line 106: "Lint, format and type-check the changes on branch {branch} in {worktree}. Report
> findings; fix nothing."

`client/` has a `package.json` and no `node_modules`, and "type-check" is an instruction to run
`tsc`. See new defect **N2**.

The money exception exists now:

> line 116: "**Fast-tests-only, with one exception:** when the brief names an integration suite and
> a database for a **critical** chunk (money, auth, tenant isolation, migration), that chunk is
> never fast-gates-only — run the suite and append its last 20 lines to `WORKER-REPORT.md` … an
> integration test the plan asks you to *write* gets written and left unrun, listed as unverified."

One sentence closes round-1 defects 2 and 8. My brief names `pytest tests/integration/billing -q`
and `acme_test`, Postgres is up → I run it, append the tail. No brief-vs-skill collision left.

### Step 4 — AC-check (counterfactual)

> line 129: "Run when the brief orders an AC-check, or — brief silent — when `review.cross` … is
> true (its default). Explicit brief beats the flag either way."

`review.cross: false`, brief orders it → I run it. Round-1 defect 5 gone. The
"do **not** run `/we:ac-review` as a separate pass" sentence now sits in the AC step it describes
(round-1 defect 11).

### Step 5 — Push (counterfactual)

> line 151: "`git push -u origin {branch} && git ls-remote --heads origin {branch}`" …
> "An empty `ls-remote` means the push did not land — that is a blocker, not a done."

`-u` plus verification. The brief's "NEVER report done without a pushed branch" now has a
mechanism behind it.

### Step 6 — Report (counterfactual)

`WORKER-REPORT.md`, "never `git add` it", "plus the critical-gate output if Step 3 ran one", then
the fully written `SendMessage` with `to=`, `summary=`, the field list, and the note that
`SendMessage` is a deferred tool needing `ToolSearch` first. Round-1 defects 3 and 10 gone. The
skill's field list adds `questions:` over the brief's — a superset, and the right one.

## Round-1 verdict table

| # | Round-1 defect (short) | Verdict | Evidence (quoted line or its absence) |
|---|---|---|---|
| 1 | No brief-vs-skill precedence rule | **FIXED** | line 19: "The Lead's brief outranks every default in this skill … The brief is silent → the step applies." |
| 2 | No critical/money exception to fast-gates | **FIXED** | line 116: "when the brief names an integration suite and a database for a **critical** chunk (money, auth, tenant isolation, migration), that chunk is never fast-gates-only — run the suite and append its last 20 lines to `WORKER-REPORT.md`" |
| 3 | `WORKER-REPORT.md` absent from the skill | **FIXED** | line 160: "Write `WORKER-REPORT.md` in the worktree root … plus the critical-gate output if Step 3 ran one. It is not part of the change: never `git add` it." |
| 4 | No channel for a plan-vs-ticket conflict | **FIXED** | line 25 ("the only channels out are `WORKER-REPORT.md` and exactly one `SendMessage`") + line 50 ("A comment that **changes scope** … stop and hand it back as a question; re-planning is the refine lane's job"). Residual, not a downgrade: `references/ticketing.md` line 12 still says "you name the conflict to the user" — the skill overrides it locally, the reference was not revised. |
| 5 | `review.cross: false` vs. a brief ordering the AC-check | **FIXED** | line 129: "Run when the brief orders an AC-check, or — brief silent — when `review.cross` … is true (its default). Explicit brief beats the flag either way." |
| 6 | Finish-first bullet self-contradicts on a money-path seam finding | **FIXED** | Rules line 182: "The exception is a **money-path** finding — fix it in its own commit *and* raise it as a question, so the Lead can revert it at integration." Exactly the prescribed tiebreak. (The unresolved wording survives in `orchestrate/SKILL.md`'s Worker-Brief — filed as N3, not charged to this file.) |
| 7 | No `Co-Authored-By` trailer in the commit format | **FIXED** | line 96: "`Co-Authored-By: <Engine> <Model> <noreply@…>`" inside the commit block. Placeholders still resolved by the worker — same latitude as orchestrate line 524. |
| 8 | Plan assigns an integration test the skill forbids running | **FIXED** | line 120: "an integration test the plan asks you to *write* gets written and left unrun, listed as unverified." |
| 9 | Step 4's gate agents have elided arguments | **PARTIALLY** | The `we:test-runner` prompt now carries both rules round 1 named (line 110). The `we:static-analyzer` prompt carries neither and actively orders the forbidden tool: line 106 "Lint, format and **type-check** the changes … Report findings; fix nothing." Half the fix landed. → N2. |
| 10 | `SendMessage` named but not specified | **FIXED** | lines 164–171: "send exactly one message (`SendMessage` is a deferred tool — `ToolSearch` for it first)" with `to="team-lead"`, `summary=`, and the field list. |
| 11 | Line 132 mis-describes its own step | **FIXED** | The sentence now lives in Step 4, the AC step: line 140 "Do **not** run `/we:ac-review` as a separate pass, and do **not** bug-hunt". |
| 12 | No generated-artifact step | **FIXED** | line 88: "Regenerate what the brief lists as a generated artifact (OpenAPI schema, typed client) and commit it; leave gate-baseline files (coverage ratchets, allowlists) to the Lead." |
| 13 | Nothing warns about a concurrent sibling chunk on a shared file | **FIXED** | line 76: "a phase grouped with yours may be building right now, so treat any file listed under it as a shared seam and say so in your report." |
| 14 | CUT: parallel-`Agent()` block, model-tier paragraph, duplicate Rules bullet | **FIXED** | All three gone. line 74 replaces them with the reason ("phases in one worktree share one git index, so two concurrent committers race `.git/index.lock`"); model tiers moved to the reference list, line 191. |
| 15 | CUT: DoR-lite on an already-scanned approved plan | **FIXED** | line 45: "**Standalone invocation only** (no Lead brief) … A briefed worker skips it — the Lead ran it before dispatch." |
| 16 | CUT: Step 2's worktree-detection prose for a briefed worker | **FIXED** | Step 1 is three lines, and the round-1 dangling case is closed: line 61 "Run the bootstrap the brief names, unless it says the worktree is already bootstrapped." The detection sentence stays because standalone invocation needs it. |

**Tally: 15 FIXED / 1 PARTIALLY / 0 STILL OPEN.**

## New defects introduced by the revision

**N1. `[CLARITY]` — the new precedence rule can swallow the new stop branch, on the run's biggest
decision.** Line 19: *"**The Lead's brief outranks every default in this skill.**"* Line 22: *"The
brief is silent → the step applies."* Line 52: *"A comment that **changes scope** … is not yours to
absorb — stop and hand it back as a question."* My brief is an unconditional order to build
(`implement phase 2 → … → push → STOP`), so a worker can hold that the brief has spoken on whether
to build, making the Step-0 stop a default it outranks. The only thing narrowing line 19 is its own
enumeration — *"a worktree, branch, test discipline, gate list or integration suite"* — and a stop
branch is not in that list, so the general sentence and the enumeration point opposite ways.
Outcome divergence: an entire dispatch built on a scope the Lead never approved, versus a clean
hand-back. *Fix:* one clause — "a stop branch in this skill is not a default; only a brief that
names the same fact overrides it."

**N2. `[MISSING MECHANIC]` — the `we:static-analyzer` prompt orders the tool the worker may not
run.** Line 106: *"Lint, format and type-check the changes on branch {branch} in {worktree}. Report
findings; fix nothing."* The no-node-tooling rule and the report-what-you-skipped rule live only in
the sibling `we:test-runner` prompt (line 112: *"Do not run `yarn`/`npm install`, `jest` or `tsc`
in a worktree without node_modules — report that as skipped"*). This repo has `client/package.json`
and no `node_modules`; "type-check" is an instruction to run `tsc`; the brief forbids installing
and requires the skipped frontend validation to be reported. The agent either installs (violating
the brief), fails opaquely, or silently reports nothing about `client/`. *Fix:* move that sentence
into both prompts, or lift it above the block as a rule for both.

**N3. `[CLARITY]` — cross-artifact: `orchestrate/SKILL.md`'s Worker-Brief still carries the
contradiction the skill just resolved.** Not a defect in the file under test, but it reaches this
worker. The brief template (orchestrate lines 307–310) still says *"a small finding (≤ ~30 min) on
the seam you touch gets FIXED in your branch … Product decisions, **money-path changes** and
foreign-subsystem redesigns go back to the Lead as QUESTIONS"* — the exact round-1 defect-6
sentence, unrevised. Under line 19 a worker may read the brief as outranking Rules line 182 and
report the currency bug away instead of fixing it in its own commit. The skill's fix is right; the
artifact that reaches the worker first has not caught up. *Fix:* mirror line 182's wording into the
Worker-Brief template — `orchestrate/SKILL.md` line 336 already commits to exactly that
("When a rule changes, update the owner AND the brief").

**N4. `[CLARITY]` — Step 3 appends to a file Step 6 creates.** Line 118 tells me to *"append its
last 20 lines to `WORKER-REPORT.md`"*; the file is written three steps later (line 160). A worker
that reads in order runs the suite, keeps no capture, and reconstructs the tail from memory or
loses it. One clause ("redirect the run to a file and paste the tail in Step 6") closes it.

## Grade

**4/5.** Fifteen of sixteen round-1 defects are genuinely closed, and the closures are the right
kind: mechanics, not prose. The two that changed outcomes both landed — a money chunk now runs its
integration suite and pastes the evidence, and a report now reaches a named recipient through a
fully written call instead of being printed into a void. The one that changed *this* run landed
too: round 1 quietly narrowed a story's scope on its own authority; the revised Step 0 hands it
back to the refine lane, and I derived that from the file instead of reconstructing it from
`orchestrate/SKILL.md`. Every fork round 1 had to guess — precedence, channel, money-path tiebreak,
write-but-don't-run, AC-check vs. `review.cross` — is now answered in the text. It is not a 5 for
two reasons. N1 is real and sits on the highest-stakes decision in the scenario: line 19's
"outranks every default" and line 52's stop branch can be read as contradicting each other, so two
competent workers given this brief can split on whether to build at all. N2 is a half-landed fix:
one of the two gate prompts got the rules, the other got an instruction to run the exact tool the
brief forbids. On length: ~194 lines carrying strictly more mechanics than round 1's, with all four
`[CUT]` items actually removed and model tiers pushed to the reference — the file is shorter where
it was dead and longer where it was silent. That earns itself; the only residual fat is the intro's
`--solo` aside and the four-item reference list at the bottom.
