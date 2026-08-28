# SIM-1 · ci-review · Round 2 · Scenario B

Table-top run of the REVISED `we/skills/ci-review/SKILL.md` (285 lines, was 335) as the main
agent, invoked as `/we:ci-review` in `the host repo` on `feat/TICKET-000-projection` / PR #3718.
Nothing was executed. Line numbers below are the NEW file's.

---

## Trace

### The three demanded answers, up front

- **Does the run terminate? Yes.** `gh pr view $PR --json mergeable,mergeStateStatus,autoMergeRequest`
  is now inside 1a's own bash block (L83), so `CONFLICTING/DIRTY` is in hand before a single
  poll. **There is zero blind waiting before the diagnosis** — round 1's unbounded loop is gone.
  The only wait in the run is `gh pr checks $PR --watch` *after* the base-merge push, and it is
  bounded twice: L140 (*"**Never started** → check merge state (1a) before waiting"*) and
  L164-166 (*"if it is still pending after ~2× its usual runtime, report that rather than
  blocking indefinitely"*).
- **Migration heads: I stop and ask, I do not patch.** 3f L242-243: *"If the second head came in
  from the base branch, the merge-heads migration belongs on the base branch, not as a
  per-branch patch — say so and ask rather than patching around it."* That is exactly
  the host repo's CI rules file L75-76. Round 1's forbidden per-branch
  merge migration is no longer ordered.
- **The human thread: surfaced before fixing, never resolved, still not gating.** 1d L157-158:
  *"**Surface human-authored threads to the user NOW**, before fixing — one may say the code is
  intentional and make a bot finding moot. Never auto-resolve them."* I raise `maintainer`'s "warum
  projizierst du hier zweimal?" to the user in Phase 1. 3e L227 is unchanged: *"Human threads do
  not block this gate; list them in the report."* Nothing tells me whether to **wait** for the
  answer.

### Phase 1a — Resolve the run's state (L74-91)

1. `Bash:` the L79-83 block verbatim → `GH_AVAILABLE=true`, `PR=3718`,
   `REPO=the app repo`, `OWNER=the host repo-ai`, `REPO_NAME=the host repo`, `BASE_REF=main`,
   and `{"mergeable":"CONFLICTING","mergeStateStatus":"DIRTY","autoMergeRequest":null}`.
2. L89-91 fires: *"required checks may never start; a check pending with no run behind it is a
   merge conflict, not a slow job. Merge or rebase `origin/$BASE_REF` first, push, and let the
   checks fire — waiting cannot fix it."*

   Decision point the skill leaves to me. I take **merge**, not rebase — but only because I read
   3f L240-242 later; at L89 the word `rebase` stands bare. `git fetch origin main` →
   `git merge origin/main` → **conflicts** (the PR is `CONFLICTING` by construction). The skill
   warns about a conflicted *rebase* at L241-242 and says nothing about a conflicted merge. I
   hand-resolve, including whatever `down_revision` hunk the migration carries.
3. `Bash: git push` — the unblocking push L90 orders. **Three things the skill does not say
   here**: (a) whether this push is exempt from L15's *"Fix everything. Push once. No leftovers"*
   and 3g L246-248's push gate; (b) that 3f's one-head check applies to *this* merge — so main's
   second alembic head is now merged into the branch and **pushed**, ~150 lines before the rule
   that guards it runs; (c) that the reviewers re-run against the new head, so everything I am
   about to collect will be stale within minutes. See New defects 1 and 2.
4. Checks fire. `Bash: gh pr checks 3718 --watch` (L164).

### Phase 1b — Collect (L93-120)

1. `gh pr checks 3718` — source 1.
2. GraphQL `reviewThreads … isResolved==false` (L103-107) → two nodes:
   `coderabbitai[bot]` nitpick at `…/projection.py:88`; `maintainer` at `…/projection.py:141`.
3. `gh api repos/…/pulls/3718/reviews --jq '…endswith("[bot]")…'` (L110-112) → CodeRabbit
   summary, nothing new.
4. `gh api repos/…/issues/3718/comments --paginate --jq '… test("VERDICT:|SEV:|Code Review") …'`
   (L117-119) → the `claude[bot]` "## Code Review" comment: one `<!-- SEV:WARNING -->`
   ("the new migration has no down_revision test") + `<!-- VERDICT:WARNING -->`.

### Phase 1c (L122-140)

No concluded non-pass rows at the moment of collection. L140's *"**Never started** → check merge
state (1a) before waiting"* is the row round 1 said was missing; it is present and already
consumed at step 2.

### Phase 1d — Findings table (L142-158)

| # | Source | Bot? | Severity | File:Line | Issue | Thread ID | Action |
|---|---|---|---|---|---|---|---|
| 1 | claude[bot] comment | — | **WARNING** (`SEV:WARNING`) | `alembic/versions/20260826_add_projection.py` | no `down_revision` test | — | MUST fix (L32) |
| 2 | CodeRabbit thread | yes | NITPICK | `…/projection.py:88` | extract dict literal | `PRRT_…coderabbit` | fix (finish-first, L49-52) |
| 3 | `maintainer` thread | **no** | unmarked | `…/projection.py:141` | "warum projizierst du hier zweimal?" | `PRRT_…maintainer` | **surface to user NOW** (L157) |

Row 1 survives the green `claude-review` row only because L174 requires *"zero open SEV
findings"*. L21-22 read on its own — *"the gate is the check's conclusion, not the comment"* —
points the other way. See Round-1 verdict 13.

Row 3: I put the German question to the user before touching code, per L157-158. The skill never
says whether to block on the answer, so I ask and keep working.

### Phase 2 — Triage (L170-177)

Not green (L174's three conditions fail on "zero open SEV findings"). Proceed.

### Phase 3a-3c (L180-198)

1. `Read` the migration + the existing migration-test module; `Edit` a `down_revision` chain
   assertion. `Edit` `projection.py` to extract the dict literal. No commit between fixes (L185).
2. 3b: `/we:static` + `/we:test` over the changed surface, plus `ls scripts/check-*.sh` and the
    matching gates (L190-191).
3. 3c: ONE commit, `fix: address CI and review findings`, body carries `TICKET-000` — L197 now says
    *"the ticket key in the body when the branch carries one"*, so round 1's literal `{TICKET}`
    is gone. `git commit … && git log --oneline -1`.

### Phase 3d/3e — Resolve + hard gate (L200-235)

1. `REVIEW_ALLOWLIST=$(jq …)` (L207) — defined once now.
2. GraphQL select bot threads → one id (CodeRabbit) → `resolveReviewThread` → `isResolved:true`.
    The human thread is left alone (L203-204).
3. Re-run with `| length` → 0. Checklist L232-235 walked: row 1 Fixed, row 2 Fixed, no skipped
    BLOCKING needing a PR comment, 0 unresolved bot threads, human thread surfaced.

### Phase 3f — Migration branches (L237-243)

1. `git fetch origin main` (already merged at step 2). `cd src/backend && alembic heads`
    → **two heads**. The second came in from `main`.
2. L242-243 → **I stop and ask the user**: the merge-heads migration belongs on `main`.

### Phase 3g — Push (L245-252)

Condition (c) does not hold, so **the fix commit is not pushed**. End state:

- main's second head is on the branch and on the remote (pushed at step 3),
- the fix commit sits local,
- the CodeRabbit thread is **already marked resolved** on the PR with none of its fix on the
  remote — round-1 defect 6, unfixed, biting in this exact scenario,
- the run stops on a question to the user.

### Phase 4 / Phase 5

Phase 4 not entered (default single pass, L54-58 / L256-260). Phase 5 reports. The terminal-state
list L266-273 has no row that fits "stopped mid-flow on a user decision" — state 3 is *"Blocked,
nothing to fix"*, and here there is plenty to fix.

---

## Round 1 verdicts

| # | Round-1 defect | Verdict | Evidence (new line numbers) |
|---|---|---|---|
| 1 | Push gate has no liveness condition — run does not terminate | **FIXED** | L140 *"**Never started** → check merge state (1a) before waiting"* + L164-166 *"still pending after ~2× its usual runtime, report that rather than blocking indefinitely"* — a terminal state exists on every branch; the new 1a/3g collision changes *which* state I reach, not whether I reach one. |
| 2 | Mergeability never read | **FIXED** | L83 `gh pr view $PR --json mergeable,mergeStateStatus,autoMergeRequest` in 1a's block, and L174 makes the green-STOP conditional on *"every required check concluded non-red"*. |
| 3 | 3e-bis orders the per-branch alembic patch the repo rule forbids | **FIXED** | L242-243 *"the merge-heads migration belongs on the base branch, not as a per-branch patch — say so and ask"*, matching the host repo's CI rules L75-76. (No `.claude/rules/` precedence line was added, but no contradiction remains.) |
| 4 | Assumes a rebase that cannot succeed; hides a force-push | **PARTIALLY FIXED** | 3f L240-242 names it well — *"**Prefer merge over rebase** — a rebase of pushed commits forces `--force-with-lease`, which is a user decision"* — but L89 still reads *"Merge **or rebase** `origin/$BASE_REF` first"* bare, so an agent that rebases at 1a hits round 1's dead end unchanged. |
| 5 | Human thread has no severity, no verdict, does not block | **PARTIALLY FIXED** | L157-158 moves it forward — *"Surface human-authored threads to the user NOW, before fixing"* — but L227 is unchanged (*"Human threads do not block this gate"*) and no line says whether to wait for the answer. |
| 6 | 3d resolves threads before a gate that can fail | **STILL OPEN** | 3d (L200) still precedes 3f (L237) with no caveat; in this run the CodeRabbit thread is resolved at step 13 and 3f L243 stops the run at step 16 with the fix unpushed. |
| 7 | Rules block retells the steps | **FIXED** | The file ends at Phase 5 (L280-285); there is no `## Rules` section. |
| 8 | `--ci-only` defined only in the Rules block, never handled | **FIXED** | L24-25 in the body: *"`--ci-only` narrows the run to CI: collect sources 1 and 4 only, skip thread collection and the 3d/3e thread steps, still fix and push."* |
| 9 | Duplicated ownership of severity policy + Claude-comment fact | **PARTIALLY FIXED** | Severity now one table (L29-33); the comment-vs-thread fact once (L154-156); allowlist once (L207). Residue: the "a red check is a finding even with no comment" fact is stated three times — L21-22, L123-124, L174. |
| 10 | `$REVIEW_ALLOWLIST` used before it is defined | **PARTIALLY FIXED** | L150 now carries the forward pointer *"matches `$REVIEW_ALLOWLIST` (see 3d)"*, but the definition is still 57 lines later at L207. |
| 11 | `{TICKET}` undefined placeholder | **FIXED** | L197 *"the ticket key in the body when the branch carries one"* — prose, no placeholder. |
| 12 | 1c's table has no row for "pending, job never started" | **FIXED** | L140 adds exactly that row. |
| 13 | Green `claude-review` row vs `VERDICT:WARNING` marker — no tie-breaker | **PARTIALLY FIXED** | The finding survives, but only via L174's third clause *"zero open SEV findings"*; L21-22 states the principle one-directionally — *"A red required check that posted no finding is still red: the gate is the check's conclusion, not the comment"* — which read generally tells me to downgrade a SEV behind a green row. No line says the marker outranks a stale-green row. |
| 14 | Confirmation path for MUST-fix `SEV:*` findings is default-disabled | **STILL OPEN** | L155-156 still clears a SEV row *"by the re-review after the push posting a passing verdict"*, i.e. Phase 4; Phase 4's opt-in list (L55-57: *"a fix you are unsure of, a flaky check, interdependent findings, a high-stakes PR"*) never gained the "unconfirmed SEV finding" entry. |
| 15 | Whole procedure has a second owner in `references/integration-pipeline.md` | **STILL OPEN — and now diverged** | `integration-pipeline.md` L178 still says *"**Wait for CI to conclude** (`gh pr checks {PR}` shows no `pending`/`in_progress`)"* — round-1 defect 1 verbatim — while L170-171 forbids `Skill(skill="ci-review")`. The fix is therefore **unreachable on the orchestrate path**. `we/quality/dod.md` L126-128 remains a third statement of the severity scale. |
| 16 | Phases end in prose, not checkable criteria | **STILL OPEN** | Only 3e L232-235 has `- [ ]` items; Phases 1, 2, 3a-3c, 3f, 4 and 5 end in prose, and Phase 5 (L282-285) is a list of report contents. |
| 17 | Frontmatter triggers are synonyms of one branch | **STILL OPEN** | L7 unchanged: `"/we:ci-review", "fix ci", "fix reviews", "ci failed"` — "fix ci" and "ci failed" reach the same branch, and `--ci-only` (the only real branch) has no trigger phrase. |

---

## New defects

### 1. 1a orders a merge-and-push whose three guardrails all live 150 lines downstream. **MAJOR**

> L89-91: *"**`mergeable: CONFLICTING` / `mergeStateStatus: DIRTY`** → … Merge or rebase
> `origin/$BASE_REF` first, push, and let the checks fire — waiting cannot fix it."*

Everything that makes that instruction safe is in 3f/3g and unreferenced from 1a:
the rebase→`--force-with-lease` hazard (L240-242), the one-head check (L237-243), and the
push-once gate (L15, L182, L246-248). Concretely here: the 1a merge carries **main's second
alembic head into the branch and pushes it**, before 3f ever runs — so the skill's own safety
rule guards an action that already shipped. The agent must also guess whether this push is exempt
from *"Fix everything. Push once. No leftovers."*

**Smallest fix:** one clause in 1a — *"3f's one-head check and its merge-over-rebase caveat apply
to this merge; this unblocking push is exempt from 'push once'."*

### 2. Nothing says to re-collect after the 1a unblocking push. **MAJOR**

That push creates a new head; CodeRabbit and `claude-review` re-run against it and may post
different findings. Phase 1→2→3 is linear, and the only re-collect (*"re-collect all sources"*,
L262) sits in the opt-in, default-off Phase 4. Followed literally I triage the pre-merge
findings and ship fixes against a review of a commit that is no longer the head.

**Smallest fix:** append to L91 — *"then return to 1b: the reviewers re-run against the merge."*

### 3. Terminal states have no row for "stopped to ask the user". **MINOR**

> L242-243: *"say so and ask rather than patching around it."*
> L266-273: the three terminal states are Green · Cap reached, still red · *"Blocked, nothing
> to fix"*.

3f's stop-and-ask is the state this run actually ends in, and it fits none of them — there is
plenty to fix, it is not a cap, it is not infrastructure.

**Smallest fix:** a fourth state — *"4. **Stopped on a user decision** — a gate needs an answer
only the user can give (3f's base-branch head). Report what is committed, what is pushed, and
the question."*

### 4. A conflicted MERGE has no guidance, and the risky hunk is the migration chain. **MINOR**

L240-242 warns only about a conflicted *rebase*. 1a orders a merge on a PR that is `CONFLICTING`
by definition. Resolving conflicts is something I do unprompted — but hand-resolving a
`down_revision` conflict silently produces a wrong revision chain that no local gate catches.

**Smallest fix:** in 3f — *"A conflict in a migration's `down_revision` is not a text merge:
re-derive the chain from `alembic history` before committing the resolution."*

### 5. `--ci-only` is described as narrowing "to CI" but keeps a review source. **INFO (wording)**

> L24-25: *"`--ci-only` narrows the run to CI: collect sources 1 and 4 only"*

Source 4 is bot review summary comments. Including it is **correct** — the `claude-review`
verdict comment is the CI gate's payload — but the sentence reads as a contradiction.

**Smallest fix:** *"…sources 1 and 4 (the verdict comment IS the gate's payload)…"*

---

## What I needed and did not find

Strictly mechanics a fresh Opus would **not** supply unprompted, because the skill's text points
elsewhere or is silent:

1. **Whether 1a's unblocking push is exempt from "push once".** L15 and L246-248 say push once;
   L90 orders a push. No precedence.
2. **Whether to check `alembic heads` before that 1a push.** 3f owns the check and runs after.
3. **Whether to wait for the user's answer on the human thread.** L157 says *surface NOW*; L227
   says it does not block. Surface-and-proceed and surface-and-wait are both readings.
4. **Whether to re-collect after the unblocking push** (New defect 2).
5. **A precedence line for `.claude/rules/`.** Round 1's contradiction is gone by accident of
   agreement, not by a stated rule; the next divergence has no tie-breaker.
6. **Which Claude signal wins when the check row and the `VERDICT:` marker disagree** — L21-22
   still frames the check conclusion as authoritative.

Excluded because I would do them anyway: resolving merge conflicts, reading a file before
editing, running affected tests, one commit not five, `git log -1` after commit, not resolving a
human thread.

---

## What could still be cut

The file is genuinely tighter — the Rules block is gone, the severity policy has one owner, the
allowlist is defined once. Remaining no-ops and duplication, ~18 lines:

- **L13** — *"Collects findings from CI + reviews, fixes them, and pushes once everything is
  addressed."* Restates the frontmatter description and L15's core principle. Cut.
- **L21-22 / L123-124 / L174** — the "a red check with no comment is still a finding" fact,
  three times. Keep 1c's (L123-124), cite it from the other two. Fixing this also fixes
  round-1 defect 13's residue if L21-22 is made bidirectional.
- **L182** — *"⛔ **ONE continuous flow, in order. Do NOT jump to `git push`.**"* The steps are
  numbered 3a-3g and 3g states its own preconditions. A no-op under plugin-authoring L68-70;
  round 1 flagged it and it survived.
- **L54-58 vs L256-260** — "One pass by default" and Phase 4's preamble still restate each
  other nearly clause for clause (default stop · the exception list · the user budget replacing
  the cap). Keep L54-58; reduce L256-260 to *"Enter only under the single-pass exceptions above."*
- **L95-96** *"Do not special-case a reviewer by name"* and **L152** *"never from the reviewer's
  name"* — one statement suffices.
- **L192-193** — *"The full suite and the coverage gate run in CI."* Rationale, not behaviour.

The reclaimed space more than covers New defects 1-3, which are all one-clause fixes.

---

## Grade

**3/5.** The scenario now resolves without a hang and without violating the repo's alembic rule —
both round-1 BLOCKERs are genuinely closed, and 1a's merge-state read is the single highest-value
edit in the revision — but "no guessing" fails on three unresolved questions (is the 1a push
exempt from push-once, must I re-collect after it, do I wait on the human thread), and the first
of those is not benign: following the text literally pushes main's second alembic head onto the
branch before the rule that forbids it ever runs.
