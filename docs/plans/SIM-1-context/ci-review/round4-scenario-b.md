# SIM-1 · ci-review · Round 4 · Scenario B

Table-top run of the thrice-revised `we/skills/ci-review/SKILL.md` as the main agent, invoked as
`/we:ci-review` in `the host repo` on `feat/TICKET-000-projection` / PR #3718. Nothing was
executed.

**Line numbers:** the file on disk is **295 lines** (`wc -l`), not 294. My first `Read` render
disagreed with the disk at two lines (L97, L148 — it showed the round-3 text); `grep`/`awk`
against the file settled both. Every number below is the disk file's, verified by `awk`.

---

## Trace

### The five demanded answers, up front

- **Does it collect everything before stopping? Yes.** L86 — *"Note it and **keep collecting** —
  the reviews that did post are valid findings"* — is unambiguous, and the conflict is explicitly
  re-labelled *"a push-time problem"* (L86-87). All four sources of 1b run. Round-3 MAJOR 1 is
  closed.
- **Does it fix the WARNING and the nitpick? Both, yes.** The `SEV:WARNING` (migration has no
  `down_revision` test) is MUST-fix under L34 and survives Phase 2 via L172's *"zero open SEV
  findings"*. The CodeRabbit nitpick is a ≤30-min fix on the seam this PR touches (L34 *"should"*
  - L50-51 finish-first) → fixed, not skipped.
- **The conflict:** merged, not rebased, at 3f (L242-245), hand-resolved. Never a force-push.
- **The second head:** `alembic heads` → two, second from `main`. L245-248 owns the outcome:
  merge-heads migration belongs on `main`, *"push what you fixed, report the two heads as the
  blocking question, and stop at terminal state 3"*.
- **The human thread:** surfaced to the user at 1d (L155), never auto-resolved (L156, L230),
  reported verbatim (L295). Whether to **wait** for the answer is still unstated (R1-5, third
  round open).
- **Terminal state: 3.** Named by L247 itself, so Phase 5 L294 has a slot for it.

### Phase 1a — resolve the run's state (L64-89)

1. L66-70's fresh-shell rule read first.
2. `Bash:` the L71-79 block verbatim → `GH_AVAILABLE=true`, `PR=3718`, `REPO=the app repo`,
   `BASE_REF=main`, `REVIEW_ALLOWLIST` from `.weside/config.json`, and
   `{"mergeable":"CONFLICTING","mergeStateStatus":"DIRTY","autoMergeRequest":null,"state":"OPEN"}`.
3. L84-86 fires and *explains the world state exactly*: `core-required` and `Backend (Test)`
   pending with no run behind them are the conflict, not slow jobs. I note it and continue. No
   merge, no push, no wait here — the whole merge moved to 3f.

### Phase 1b — collect (L96-118), four calls

| Call | Result |
|---|---|
| `gh pr checks 3718` (L98) | 5 rows: `core-required` pending · `Backend (Test)` pending (40 min, no run) · `claude-review` pass · `codex-review` pass · `CodeRabbit` pass |
| GraphQL review threads (L101-105) | 2 unresolved: `coderabbitai[bot]` nitpick · `maintainer` (human) *"warum projizierst du hier zweimal?"* |
| latest bot review bodies (L108-110) | nothing new beyond the threads |
| bot issue comments filtered on `VERDICT:\|SEV:\|Code Review` (L115-117) | `claude[bot]` **## Code Review**: one `<!-- SEV:WARNING -->` (migration has no `down_revision` test) + `<!-- VERDICT:WARNING -->` |

L97's comment now says *"(add --required for the gate alone)"*, so I run a fifth call,
`gh pr checks 3718 --required`, to know the gate's membership. Per the host repo's CI rules L8-9 the
required set is `CI Summary`, `claude-review`, `codex-review`, and *"an absent check is not a
passing check"* — scenario B's five rows contain no `CI Summary`. See New defect 4.

### Phase 1c — non-pass checks (L120-138)

Two pending rows. There is no run-id, so L127's `gh run view --log-failed` has no argument; L138
(*"**Never started** → check merge state (1a) before waiting"*) is the applicable bullet and 1a
already answered it. Both rows are entered as blocked-by-conflict, cleared by 3f's merge — **not**
as code findings and **not** as re-runs. No blind waiting anywhere; L162-163 says the same thing
from 1e's side.

### Phase 1d — findings table (L140-156)

```
| # | Source            | Bot? | Severity | File:Line          | Issue                         | Thread ID | Action        |
| 1 | claude[bot] comment | yes | WARNING  | migration versions/ | no down_revision test         | —         | Fix           |
| 2 | coderabbitai[bot]   | yes | Nitpick  | <path>:<line>       | extract this dict literal     | <id>      | Fix (cheap)   |
| 3 | maintainer              | no  | —        | <path>:<line>       | "warum projizierst du hier zweimal?" | <id> | Surface, never resolve |
| 4 | core-required       | —   | BLOCKING | —                   | pending, no run: merge conflict | —       | 3f merge      |
| 5 | Backend (Test)      | —   | BLOCKING | —                   | same                          | —         | 3f merge      |
```

Row 1's Thread ID is `—` (L151-152), so it sits outside 3e's gate — I carry it on the Action
column instead, as L233-234 instructs. Row 3 is surfaced to the user **now**, before fixing
(L155). The green `claude-review` check row next to a `VERDICT:WARNING` comment is still
one-directional in L22-23; only L172 keeps the WARNING alive, by side effect (R1-13 open).

### Phase 2 — triage (L168-174)

Not the all-green stop. Rows 1, 2 fixed; 3 surfaced; 4, 5 owned by 3f.

### Phase 3

- **3a** — add the `down_revision`/single-head test for the new migration; extract the dict
  literal. Accumulated, uncommitted.
- **3b** — `/we:static` + `/we:test` over the changed surface, repo `scripts/check-*.sh`.
- **3c** — one commit, `fix: address CI and review findings`, `TICKET-000` in the body, `git log -1`.
- **3d** — resolve the CodeRabbit thread (fixed). `maintainer`'s thread left alone.
- **3e** — hard gate: 0 unresolved bot threads ✓ · row 1 Action=Fixed ✓ · human thread surfaced ✓.
- **3f** — `git fetch origin main` → `git merge origin/main` → conflicts (the PR is `CONFLICTING`
  by construction). L243-244 now says to resolve them *"the way you would any conflict"* — real
  guidance where round 3 had none, though still nothing specific to a `down_revision` hunk.
  Then `cd apps/backend && alembic heads` → **two**, second from `main`. L245-248 → the
  merge-heads migration belongs on `main`; **push what I fixed**, report the two heads, stop at
  terminal state 3.
- **3g** — three separate lines forbid the push 3f just ordered. See New defect 1. I take 3f's
  reading (it is the specific instruction and names the push and the terminal state in one
  sentence), so: `git push` — merge commit included, which carries `main`'s second head onto the
  branch.

### Deliverable

Findings table with five rows, two fixes shipped, CodeRabbit thread resolved, `maintainer`'s question
surfaced verbatim, one push, terminal state 3 with the blocking question: *"`main` has a second
Alembic head; the merge-heads migration belongs on `main`, not on this branch."* Strictly more
than round 3 delivered, and more than round 2.

---

## Round 3 verdicts

| # | Round-3 defect | Verdict | Evidence (295-line file) |
|---|---|---|---|
| **New-1 (MAJOR)** | The stop landed before the only collection step; the run delivered nothing | **FIXED** | L86 *"Note it and **keep collecting** — the reviews that did post are valid findings. The conflict is a push-time problem"* (L86-87). All of 1b, 1c, 1d, Phase 2 and Phase 3 now run. Exactly the fix round 3 asked for, done more cleanly than proposed (the merge moved out of 1a instead of a collect-anyway clause being bolted on). |
| **New-2 (MAJOR)** | *"apply 3f's one-head check"* did not say how much of 3f it imports | **FIXED** | The phrase is gone. 3f L242-248 owns the merge, the head check and the stop-and-ask in one block; 1a L87 only points at it (*"resolve it in 3f by merging"*). No import, no ambiguity. |
| **New-3 (MINOR)** | Nothing said what to do with the hand-resolved merge while blocked | **FIXED (with a cost)** | L247 *"push what you fixed"* answers keep/commit/abort. The cost is New defect 1: three other lines forbid that push. |
| **R3 New-3 / R2 New-3 (MINOR)** | Terminal states had no row for "stopped to ask" | **FIXED as routing, INFO on the label** | L247 routes it explicitly: *"stop at terminal state 3"*. But state 3 (L282-283) is *"**Blocked, nothing to fix** — infrastructure red after a re-run, or a BLOCKING you skipped as factually wrong"* — neither disjunct describes this run, and there **is** something to fix (on `main`, by a human). The label now lies about the state it is the destination for. |
| **New-4 (MINOR)** | The `--required` read sits outside the collection that feeds the table | **PARTIALLY** | L97's comment gained *"(add --required for the gate alone)"* — a real nudge — but L98 is still the bare `gh pr checks $PR`, `--required` is still owned by prose at L19-20, and 1d (L142-143) still has no row type for a required check **absent** from the output. Scenario B's missing `CI Summary` has nowhere to land. |
| **New-5 (INFO)** | L147's allowlist pointer pointed forward past the definition | **FIXED** | L148: *"matches `$REVIEW_ALLOWLIST` (derived in 1a)"*. |
| **New-6 (INFO)** | Merge-over-rebase caveat has two owners | **STILL OPEN** | L87-88 *"not rebasing — a rebase of pushed commits needs a force-push, which is the user's call"* and L244-245 *"a rebase instead of the merge forces `--force-with-lease`, which is the user's decision, not yours"*. Same rule, two files' worth of wording, one file. `plugin-authoring.md` L12-20 wants one. |
| **R2 New-4 (MINOR)** | A conflicted MERGE had no guidance | **PARTIALLY** | L243-244 *"Resolve merge conflicts in the code the way you would any conflict"* is new and closes the bare gap. Still nothing about the migration chain — no instruction to re-derive `down_revision` from `alembic history` after resolving that hunk, which is the one conflict class this branch is guaranteed to hit. |
| **R2 New-5 (INFO)** | `--ci-only` reads as a contradiction | **STILL OPEN** | L25-26 verbatim unchanged. |
| **R1-5** | Human thread: no severity, does not block, no wait/no-wait rule | **STILL OPEN — and now load-bearing** | L155 *"Surface … NOW, before fixing"* vs L230 *"Human threads do not block this gate"*. Unlike rounds 2 and 3, 1b **is** reached this round, so the gap is live: `maintainer` may be saying the double projection is intentional, which would moot a fix I am about to ship. Nothing says whether to wait. |
| **R1-6** | 3d resolves bot threads before 3f, a gate that can stop the run | **STILL OPEN structurally, not biting here** | 3d L199 (*"MANDATORY before push"*) still precedes 3f L240 unqualified. It does not orphan the resolve **only because** I took 3f's *"push what you fixed"* reading; under 3g's reading (no push) the CodeRabbit thread is resolved on a fix that never reaches the remote. The defect's harmlessness depends on the very contradiction that is New defect 1. |
| **R1-9 residue** | "A red check with no comment is still a finding", three owners | **STILL OPEN** | L22-23, L122-123, L173. |
| **R1-13** | Green check row vs `VERDICT:WARNING` comment — no tie-breaker | **STILL OPEN** | L22-23 one-directional; the host repo's CI rules L67-68 covers only the inverse (red check + PASS comment). The WARNING survives by L172's side effect, not by a rule. |
| **R1-14** | Confirmation of a MUST-fix `SEV:*` is default-disabled | **STILL OPEN** | L152-153 clears a SEV row *"by the re-review after the push"* = Phase 4; L55-58's exception list still lacks "an unconfirmed SEV finding". This run pushes a WARNING fix and never learns whether it landed. |
| **R1-15** | The procedure has a second and third owner | **STILL OPEN — re-verified this round** | `we/references/integration-pipeline.md` L178 still *"**Wait for CI to conclude** (`gh pr checks {PR}` shows no `pending`/`in_progress`)"* with no merge-state escape — in scenario B that is an infinite wait — while L170 forbids `Skill(skill="ci-review")`. Three rounds of fixes remain unreachable on the orchestrate path. `we/quality/dod.md` L124-128 is still a third severity scale. |
| **R1-16** | Phases end in prose, not checkable criteria | **STILL OPEN** | Only 3e L235-238 carries `- [ ]` items. |
| **R1-17** | Frontmatter triggers are synonyms of one branch | **STILL OPEN** | L4-7 unchanged; `--ci-only`, the only real branch, still has no trigger phrase. |

---

## New defects

### 1. Three separate lines forbid the push that 3f orders. **MAJOR**

> L247: *"push what you fixed, report the two heads as the blocking question, and stop at terminal
> state 3"*

Against it:
- **L252 (3g a)** — *"Push only when: (a) every check has concluded"*. At 3f nothing has
  concluded and nothing can; that is the whole point of 1a's note.
- **L254 (3g c)** — *"(c) 3f holds for migration branches"*. 3f does **not** hold: the heads do
  not resolve to one. 3g's own precondition is falsified by the state 3f is in when it says push.
- **L161 (1e)** — *"**gate the push** on the long checks concluding"*.

The push is the single most consequential act in the run and the skill orders it in one place and
forbids it in three. I resolved it for 3f — specific over generic, and 3f names the push and the
terminal state in the same sentence — but that is my tie-break, not the text's, and the two
readings differ by whether `main`'s second Alembic head lands on the remote branch.

**Smallest fix:** make 3g's precondition (c) read *"3f holds, **or** 3f ordered the blocked push"*,
and give L247 the scope it means: *"push the fix commit and the merge; the branch is then blocked
on `main`, not on you."*

### 2. 3f's push restarts the gate and then abandons it. **MAJOR**

Pushing the merge is exactly what makes `core-required` fire and `Backend (Test)` start — the two
checks that could not run for 40 minutes. The run then stops at terminal state 3 with two required
checks **freshly pending, started by its own push, unwaited**, and both will fail on `alembic
heads` anyway. Phase 5 L294 demands *"gate status per required check"*; the only honest line is
"two required checks pending because I pushed, not because I waited", and nothing in the skill
sanctions reporting a gate you just restarted — L172, L21-22 and 1e all assume the gate is either
concluded or waited on.

**Smallest fix:** at L247 — *"the push restarts the required checks; report them as pending-by-your-push
and do not wait, the two heads decide them."*

### 3. 1a orders a re-collect that no reachable step performs, with no terminus. **MINOR**

> L88-89: *"after that merge **re-collect Phase 1**, because the merge changes the diff every
> finding is judged against."*

The merge happens at 3f — **after** 1b collected, after 3a fixed, after 3c committed, after 3d
resolved the CodeRabbit thread. A literal re-collect from there re-enters Phase 1 with a resolved
thread and a committed fix, and nothing says where it terminates: it is not a Phase 4 cycle (L264
defines a cycle as *"one push plus the checks and re-reviews it triggers"*), so the two-loop cap
and the user-budget rule do not apply to it. In scenario B it never fires (the run stops at 3f),
but on any non-blocked migration branch it is an unbounded loop ordered in prose. 3f itself never
mentions it.

**Smallest fix:** in 3f, after the merge — *"re-triage the existing table against the merged diff;
do not re-enter Phase 1."*

### 4. Local validation runs before the merge and is never re-run after it. **MINOR**

3b (L186-191) validates *"over the changed surface only"* at a point where `origin/main` is not
yet in the tree; 3f merges 60 lines later and validates nothing but `alembic heads`.
the host repo's CI rules L48-50 is explicit against this: *"**A merge is a code change.** After merging
`main` into an integration branch, re-run the **full** local set — not the affected subset —
including the whole-repo scripts that have no notion of 'your diff' (`scripts/check-dead-exports.sh`,
OpenAPI freshness, `alembic heads`)."* The skill imports one third of that list and drops the rest.
On the non-blocked path this pushes a merge whose full local set was never run.

**Smallest fix:** in 3f after the merge — *"re-run the full local set (the host repo's CI rules § *A merge
is a code change*), not the 3b subset."*

### 5. Phase 5 has no slot for the blocking question. **INFO**

L292-295 lists findings table, fix summary, push status + gate status + terminal state, and
threads. L247 orders me to *"report the two heads as the blocking question"* — the single most
important line of this run's output — and Phase 5 has no bullet for it. Same shape for New defect
2's pending-by-my-push status.

**Smallest fix:** a fifth bullet — *"the blocking question, when the terminal state is 2 or 3."*

### 6. Terminal state 3's label contradicts its own new caller. **INFO**

L282-283: *"**Blocked, nothing to fix** — infrastructure red after a re-run, or a BLOCKING you
skipped as factually wrong."* L247 now routes the two-heads case here, and it is neither
disjunct — there **is** something to fix, on `main`, by a human, and I fixed two other things on
the way. **Smallest fix:** *"Blocked on someone else — infrastructure red after a re-run, a
BLOCKING skipped as factually wrong, or a fix that belongs on the base branch."*

---

## What I needed and did not find

Strictly mechanics a fresh Opus 5 would not supply unprompted:

1. **Whether 3f's ordered push actually fires** (New defect 1). Three lines say no, one says yes,
   and the answer decides whether `main`'s second head lands on the branch. My tie-break is
   reasoning, not text.
2. **How to report a gate my own push just restarted** (New defect 2). Phase 5 L294 asks for a
   status the run cannot honestly give.
3. **Whether to wait for `maintainer`'s answer before fixing** (R1-5, third round). Live this round,
   because collection is reached: his question may make the WARNING fix wrong.
4. **Which Claude signal wins** when the `claude-review` check row is green and its comment carries
   `VERDICT:WARNING` (R1-13). L22-23 still frames the check conclusion as authoritative; the
   repo rule covers only the inverse case.
5. **Where an absent required check lands** (New defect 4, partial). the host repo's CI rules L8-9 says
   `CI Summary` is required and *"an absent check is not a passing check"*; scenario B has no such
   row and 1d has no cell for it.
6. **How far the merge conflict resolution goes on the migration chain** (R2 New-4, partial).
   *"the way you would any conflict"* does not tell me to re-derive `down_revision`.
7. **A precedence line for `.claude/rules/`.** The skill and the host repo's CI rules still agree by luck;
   New defect 4 is the first place they diverge (3b's subset vs L48-50's full set) and there is
   still no tie-breaker.

Deliberately excluded, because I would do them untold: resolving merge conflicts, one commit not
five, `git log -1` after committing, not auto-resolving a human's thread, reading a file before
editing it.

---

## What could still be cut

~18 lines, all previously flagged:

- **L13** — *"Collects findings from CI + reviews, fixes them, and pushes once everything is
  addressed."* Restates the frontmatter and L15. Flagged in rounds 1, 2 and 3; still there.
- **L22-23 / L122-123 / L173** — "a red check with no comment is still a finding", three times.
  Keep 1c's; cite it from the other two. Making L22-23 bidirectional while you are there closes
  R1-13.
- **L180** — *"⛔ **ONE continuous flow, in order. Do NOT jump to `git push`.**"* The steps are
  numbered and 3g states its own preconditions. A no-op under `plugin-authoring.md` L68-70;
  flagged three times, survived three times. (It is also the fourth line arguing against 3f's
  push — cutting it removes a voice from New defect 1's contradiction without deciding it.)
- **L55-58 vs L264-266** — "One pass by default" and Phase 4's preamble restate each other clause
  for clause. Keep L55-58.
- **L93-94** (*"Do not special-case a reviewer by name"*) and **L150** (*"never from the
  reviewer's name"*) — one suffices.
- **L191** — *"The full suite and the coverage gate run in CI."* Rationale, not behaviour.
- **L87-88 vs L244-245** — the merge-over-rebase caveat, still twice (round-3 New-6).
- **L19-20's `--required` sentence** — prose owning a command no numbered step runs. L97's new
  parenthetical made this worse, not better: the rule is now in two places and executed in
  neither. Promote it into 1b as source 0 (New defect 4) or cut it.

The reclaimed space covers New defects 1-5, which are one clause each.

---

## Grade

**4/5.**

Earned, and it is real movement: both round-3 MAJORs are closed by the right fix rather than a
patch. L86's *"keep collecting"* plus moving the whole merge out of 1a into 3f means scenario B now
produces a findings table, two shipped fixes, a resolved bot thread, a surfaced human question and
a named terminal state — where round 3 produced a question and a dirty worktree, and round 2
produced no head check at all. The import ambiguity is gone because the phrase that caused it is
gone (3f owns check and stop together). L148's pointer is fixed, L97 nods at `--required`, L243's
new sentence closes the bare conflicted-merge gap, and L247 routes the stop to a terminal state so
Phase 5 has a shape to fill. No force-push, no blind wait, no invented code fix for a runner
symptom.

Withheld: the fix for round-3 New-3 planted a new MAJOR — 3f orders a push that L161, L252 and
L254 each forbid, and the tie-break is mine, not the text's. That push then restarts the two
required checks and the run walks away from them with no sanctioned way to report it. Around the
edges, 1a still orders an unbounded re-collect that no step performs, and 3b's pre-merge validation
never re-runs against the merged tree, which puts the skill at odds with the host repo's CI rules L48-50 —
the first genuine divergence from the repo rule across four rounds, and still no precedence line to
settle it. Delivers correctly now; still hands the reader the single riskiest decision.
