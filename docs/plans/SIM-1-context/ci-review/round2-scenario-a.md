# SIM-1 · `/we:ci-review` · Round 2 · Scenario A

Table-top simulation. Nothing was executed. Skill under test:
`<worktree>/we/skills/ci-review/SKILL.md` (285 lines, was 335).
Round 1 report: `round1-scenario-a.md` (its line numbers refer to the deleted 335-line file).
Authoring contract: `<worktree>/.claude/rules/plugin-authoring.md`.
Repo CI rules (read-only): the host repo's CI rules file.

Scenario unchanged: PR #3721 on `feat/TICKET-000-ledger`, base `main`. `codex-review` — required
per the host repo's CI rules — is red after 1 min and posted no comment. Its failure exists only in run
9911's log: `remote: HTTP 429 too many requests` during `actions/checkout`, then `VERDICT:ERROR`.
Everything else green; zero unresolved threads; `claude[bot]` posted `<!-- VERDICT:PASS -->` with no
SEV findings; `coderabbitai[bot]` review body is "Actionable comments posted: 0".

## Trace

**User:** "codex ist rot, mach mal /we:ci-review". No flag typed. `--ci-only` is now defined (24-25),
but nothing tells me whether a pure-CI complaint should route there on its own, so I run the full
path. Outcome is the same here — see New defect 4.

### Phase 1 — Collect

**1a (76-84).** Every variable now ships its command. I run the block verbatim:

- `Bash: gh auth status …` → `GH_AVAILABLE=true`
- `Bash: gh pr view --json number --jq .number` → `PR=3721`
- `Bash: gh repo view --json nameWithOwner …` → `REPO=the app repo`, `OWNER=the host repo-ai`,
  `REPO_NAME=the host repo`
- `Bash: gh pr view 3721 --json baseRefName --jq .baseRefName` → `main`
- `Bash: gh pr view 3721 --json mergeable,mergeStateStatus,autoMergeRequest` → `MERGEABLE`, `CLEAN`,
  `autoMergeRequest: null`

Round 1's defect 8 is gone: I no longer improvise the setup, and line 89-91's `CONFLICTING/DIRTY`
branch is inapplicable (clean), so I do not misread the red check as a merge conflict.

**1b source 1 (99-100).** `Bash: gh pr checks 3721` → the five rows, `codex-review fail 1m
https://github.example/actions/runs/9911`. Line 99's comment ("keep the run URL
column, 1c consumes it") tells me the URL is live input. Round 1 defect 2 gone.

**1b source 2 (102-107).** `Bash: gh api graphql … reviewThreads … --jq 'select(.isResolved==false)'`
with `-F pr=3721 -F owner=the host repo-ai -F repo=the host repo` → **empty**. Zero findings.

**1b source 3 (109-112).** `Bash: gh api repos/the app repo/pulls/3721/reviews --jq
'group_by(.user.login)[] | last | select(.user.login|endswith("[bot]")) | …'` →
`=== coderabbitai[bot] ===` / `Actionable comments posted: 0`. Zero findings.

**1b source 4 (114-119).** `Bash: gh api repos/the app repo/issues/3721/comments --paginate
--jq '[… select(.user.type=="Bot" or (.user.login|endswith("[bot]"))) | select(.body|test("VERDICT:|SEV:|Code Review"))] | group_by(.user.login)[] | last | .body'`
→ the `## Code Review` body with `<!-- VERDICT:PASS -->`, no `SEV:` markers. Zero rows.

Credit where due: the shape filter plus the comment at 114-116 ("a review action posts under its own
app login OR under `github-actions[bot]`, so filter by SHAPE, not by name") is the exact
the host repo's CI rules trap — *"Red `claude-review` WITH a PASS comment is the gate, not the review — the
action posts as `claude[bot]` or `github-actions[bot]`; anything grepping only one login misreads
it."* Round 1's name-matched jq would have been the wrong instrument here.

**1c (122-140) — the section that decides this scenario.** "A red or errored required check is a
finding even when no bot commented on it — and that is the case the empty findings table hides."

- `Bash: gh run view 9911 --log-failed` → `Error: fetch failed` / `remote: HTTP 429 too many
  requests` during `actions/checkout`, then `VERDICT:ERROR`.
- Classify from the log per 136-139: *"checkout/network HTTP errors … a job that errored without
  producing a verdict → **re-run it** (`gh run rerun <run-id> --failed`); do not change code to
  appease it. A re-run is not a cycle."*
- `Bash: gh run rerun 9911 --failed`

This is the correct action, reached without guessing. Round 1's defects 1, 2, 5 and 7 all fired here
and none of them does now.

**1d (143-158).** One row: `| 1 | CI (codex-review) | — | BLOCKING | — | runner error: checkout HTTP
429, VERDICT:ERROR | — | Re-run fired |`. Bot?/Severity are now legally derivable — line 152 allows
severity "from the check's conclusion". No human threads to surface.

**1e (160-166).** Nothing pending at collection time. But the re-run I just fired *is* now a pending
check, and 1e is written about the initial long-check window rather than about a re-run — see New
defect 2. I would `gh pr checks 3721 --watch`, which is what 1e's mechanism implies, not what any
line instructs for this case.

### Phase 2 — Triage (170-176)

"All green → STOP **only when all three hold**: every required check concluded non-red, zero
unresolved threads, zero open SEV findings. A red check with an empty findings table is 1c's case,
not this one — **never report green while any required check is red**."

Round 1's catastrophe cannot happen: the terminal condition is now check-colour, not finding-count.
I do not stop here.

### Phase 3 — Fix → Validate → Commit → Resolve → Push

- **3a (186).** No finding has a file. Nothing to accumulate. The ⛔ at 182 ("ONE continuous flow, in
  order") gives me no exit, and no line says "no code finding → skip to Phase 5" (defect 6, still
  open).
- **3b (188-193).** I would run `/we:static` + `/we:test` over an empty changed surface. No guard.
- **3c (195-197).** "ONE commit with all fixes … Verify HEAD moved afterwards." Nothing is staged →
  `nothing to commit` and HEAD does not move. The verification step fires on an abort that is not an
  abort. Unguarded.
- **3d (200-221).** Fresh shell: `$GH_AVAILABLE`, `$PR`, `$OWNER`, `$REPO_NAME` are unset, so
  `[ "$GH_AVAILABLE" = true ]` is false and the MANDATORY resolve step **silently no-ops**. Harmless
  here (zero threads) — New defect 1.
- **3e (224-235).** Same fresh-shell problem, but this one fails *loudly*: `-F pr=` against `Int!` is
  a GraphQL type error, and `$REVIEW_ALLOWLIST` is empty (226 explicitly forbids redefining it). The
  checklist itself is satisfiable by hand: no BLOCKING row is Fixed, so item 1 fails → I do not
  push.
- **3f (237-243).** `git diff --name-only origin/main...HEAD -- src/backend/alembic/` — my own
  test; the skill still leaves "is this a migration branch" to me. Out of scenario scope.
- **3g (245-252).** "(a) every check has concluded and its failures are folded into the fix commit."
  My failure is disposed of by a re-run, not folded into a commit, so (a) is unsatisfiable as
  written. It errs safe — I do not push — but for the wrong reason (New defect 3). With nothing
  committed the push would be a no-op anyway.

### Phase 4 / 5

`gh pr checks 3721 --watch` until `codex-review` concludes. Two outcomes:

- green → terminal state 1 (268-270), report, `autoMergeRequest` is null so nothing fires by itself;
- red the same way → 1c's "report it as infrastructure and stop" = terminal state 3 (272-273).

Both are correct endings. What no phase says is that I should wait at all, or against which budget —
Phase 4 defines a cycle as "one push plus the checks and re-reviews it triggers" (256-257) and there
was no push. Report per Phase 5 (281-285): findings table, no fixes, no push, gate status per check,
terminal state.

**Net: the revised skill lands this scenario correctly.** Zero code changes, one re-run, no false
green, no false push.

## Round 1 verdicts

| # | Round-1 defect | Verdict | Evidence (new line numbers) |
|---|---|---|---|
| 1 | Red required check with no comment → "All green" | **FIXED** | 175-176: *"A red check with an empty findings table is 1c's case, not this one — never report green while any required check is red."* |
| 2 | `gh pr checks` run URL collected and dropped | **FIXED** | 99 `# 1) CI status — keep the run URL column, 1c consumes it`; 128 `gh run view <run-id> --log-failed`. |
| 3 | Push gate measures lateness, not outcome | **FIXED** | 20-22 defines the gate as *"every required check has concluded non-red"*; 246-247 replaces "no pending" with *"every check has concluded and its failures are folded into the fix commit"*. |
| 4 | `--ci-only` undefined | **FIXED** | 24-25: *"collect sources 1 and 4 only, skip thread collection and the 3d/3e thread steps, still fix and push."* Residual scope ambiguity → New defect 4. |
| 5 | Exception taxonomy has no slot for a runner error | **PARTIALLY FIXED** | 31 gained *"or the red is the runner, not the code (see 1c)"*, but 35-38 still reads *"a finding may be skipped **ONLY when:** … factually incorrect … break existing behavior … pre-existing pattern"* — round 1's proposed fourth criterion was never added, so the two policies still disagree. Does not bite here (1c's disposition is "re-run", not "skip"). |
| 6 | No zero-findings / empty-diff branch in Phase 3 | **STILL OPEN** | 182 *"ONE continuous flow, in order. Do NOT jump to `git push`"*; 186 *"Accumulate ALL changes"*; 195-197 *"ONE commit with all fixes … Verify HEAD moved afterwards."* Nothing branches on an empty diff. |
| 7 | No re-run path; Phase 4 gated on a push | **PARTIALLY FIXED** | The mechanic exists — 138 `gh run rerun <run-id> --failed` — but 256-257 still defines a cycle as *"one push plus the checks and re-reviews it triggers"*, so a re-run without a push has no owning phase. |
| 8 | Six interpolated variables never derived | **FIXED** | 78-83 gives a command for each, including `BASE_REF=$(gh pr view $PR --json baseRefName …)   # from the PR, never assumed "main"`. |
| 9 | `$REVIEW_ALLOWLIST` used before definition | **PARTIALLY FIXED** | 150 now cites its owner (*"matches `$REVIEW_ALLOWLIST` (see 3d)"*) instead of re-stating the default, but the assignment still lives at 207 — and 76's fresh-shell rule makes that placement actively wrong (New defect 1). |
| 10 | 3b restates `/we:test`'s rules; bare `test-runner` | **PARTIALLY FIXED** | The bare agent name is gone and 190 cites the owners (*"`/we:static`, `/we:test` own the procedure"*), but 192-193 still copies two of their rules verbatim: *"derive the base ref (1a), and fall back to the full suite when the diff crosses test config or exceeds ~50 files."* |
| 11 | `## Rules` block retells the steps | **FIXED** | No `## Rules` section survives; the file ends at Phase 5 (285). |
| 12 | No checkable completion criteria | **PARTIALLY FIXED** | 232-235 is a real `- [ ]` list at the 3e gate. Phase 5 (281-285) is still four prose bullets with no `- [ ]`, so "did I report completely" stays unverifiable. |
| 13 | Unpaired negations | **FIXED** | The old bare prohibitions are gone; 155-156 states the positive (*"It is cleared by the re-review after the push posting a passing verdict"*), and 137-138, 157-158, 182 all pair. |
| 14 | Frontmatter: noun-phrase lead, synonym triggers | **STILL OPEN** | 3-7 is byte-identical: leads *"CI/Review checker and fixer"*, and *"fix ci"* / *"ci failed"* still reach one branch — while `--ci-only`, now a real second branch, has no trigger. |
| 15 | No-op lines | **FIXED** | "Read each finding, open file, make fix", the `git add`/`git commit -m` fence and line 13's "Runs in the main agent…" clause are all gone; 186 and 195-197 keep only the steering half. |

## New defects

### N1. The revision states the fresh-shell hazard and then violates it — MAJOR

> `76:` Each Bash call is a **fresh shell** — derive these in the same block that uses them, or re-derive:
> `226:` Re-run the same query with `| length` (reusing `$REVIEW_ALLOWLIST` — do not redefine it) …

226 instructs exactly what 76 forbids. The same hole is in the 3d block, which consumes four
variables it never derives:

> `209:` `if [ "$GH_AVAILABLE" = true ] && [ -n "$PR" ]; then`

In a fresh shell that test is false, so the step labelled **"(MANDATORY before push)"** at 200 does
nothing and prints nothing — while 3e's query, on the same missing variables, fails loudly on an
empty `Int!`. A silent no-op on the mandatory step and a loud error on its verifier is the worst
pairing: the failure mode reads as a GitHub problem, not as a missing derivation. Harmless in
scenario A (zero threads to resolve), fatal in the normal case.

**Smallest fix:** move 1a's derivation lines (plus `REVIEW_ALLOWLIST=`) into a named snippet and
prefix the 3d and 3e blocks with it, or state at 76 "every block below opens with 1a's derivations".

### N2. No phase owns waiting on a re-run, and no terminal state covers "re-run in flight" — MAJOR

> `138:` → **re-run it** (`gh run rerun <run-id> --failed`) … **A re-run is not a cycle.**
> `256-257:` One **cycle** = one push plus the checks and re-reviews it triggers.

After 1c fires the re-run, the run's outcome is the only thing that decides between terminal state 1
and terminal state 3 — and both (268-273) presuppose an outcome the skill never instructs me to
observe. 1e's `--watch` is written about the initial long checks, and Phase 4 is push-shaped, so the
step that closes this scenario is not owned by any phase. Waiting is something I do anyway; what the
skill owes and does not give is the **budget** — how long, and whether a re-run's failure counts
toward Phase 4's cap.

**Smallest fix:** one sentence at 139: *"then `gh pr checks $PR --watch` until it concludes; a second
identical failure is terminal state 3 and does not count against the Phase 4 cap."*

### N3. 3g's condition (a) has no clause for a failure disposed of without a commit — MINOR

> `246-247:` Push only when: (a) every check has concluded and its failures are folded into the fix commit;

A failure classified per 1c as the runner is disposed of by a re-run, and a BLOCKING skipped as
factually wrong is disposed of by a PR comment (44-47). Neither is "folded into the fix commit", so
(a) is literally unsatisfiable for both. It fails safe — I withhold the push — but for a reason the
text does not mean.

**Smallest fix:** *"…folded into the fix commit, re-run per 1c, or documented per the skip criteria."*

### N4. The gate is defined as "required checks", the collector treats every check as blocking — MINOR-MAJOR

> `19-20:` The gate is the set of checks the PR's branch protection **requires** — read it from `gh pr checks $PR`, never from memory.
> `122:` ### 1c. Every non-pass check is a BLOCKING row

The two sentences disagree. the host repo's CI rules names checks that are deliberately non-blocking
(*"CodeRabbit | nothing — opportunistic bot threads"*), and under 122 an advisory red becomes a
BLOCKING row that withholds the push. Secondarily, plain `gh pr checks` does not distinguish required
from advisory — `--required` does — so 20 names the right command and omits the one word that makes
it answer its own question.

**Smallest fix:** `gh pr checks $PR --required` at 20 and 100, and re-title 1c *"Every non-pass
**required** check is a BLOCKING row"*, with advisory reds reported but not gating.

### N5. `--ci-only`'s effect on the 3e checklist is undecided — AMBIGUITY (not a defect)

> `25:` … skip thread collection and the 3d/3e thread steps, still fix and push.

Two of 3e's four checklist items (232-233) are about BLOCKING rows and PR-comment evidence, not
threads. "The 3d/3e thread steps" leaves it open whether those two survive `--ci-only`. Pairs with
round-1 defect 14: now that `--ci-only` is a genuine second branch, the frontmatter's duplicate
triggers have somewhere legitimate to point and still don't.

## What I needed and did not find

Strictly mechanics a fresh Opus agent would **not** supply unprompted:

1. **The re-run budget.** That I should wait for run 9911's re-run is obvious; whether its second
   failure counts against Phase 4's cap, and how long "still pending" becomes "report it", is
   project convention the skill does not carry (N2).
2. **Which checks are required.** The skill asserts the gate is branch protection's required set but
   gives no procedure that returns it (N4). In this repo I know `codex-review` is required only
   because the host repo's CI rules says so — the skill points at a command that, as written, cannot tell me.
3. **Whether an infra red owes an artifact on the PR.** 44-47 requires a PR comment for a *skipped
   BLOCKING*; a runner red is dispositioned in 1c, outside that paragraph. So it is undecided whether
   this run should leave `gh pr comment 3721 --body "codex-review red = checkout 429, re-run fired"`
   behind. Without it the next human sees a red check and no explanation anywhere but my terminal.

Deliberately excluded: extracting `9911` from the run URL, waiting on `--watch`, and skipping a
commit when nothing is staged — I do all three unprompted; only the last is a defect (6), and only
because 182 forbids leaving the flow.

## What could still be cut

The revision took the large cuts round 1 named (the `## Rules` block, the four-fold "Claude review is
a comment" restatement, the `git add`/`git commit` fence, the no-op lines). ~50 lines went. What is
left is smaller and mostly duplication, not no-ops:

- **54-58 vs 256-260** — "one pass by default, a user budget outranks the default cap" stated twice
  at ~5 and ~5 lines. Keep the Phase 4 copy (it governs the phase), cut 54-58 to one sentence with a
  pointer. ~4 lines.
- **31 vs 35-38** — the severity table's "Only exception" column and the strict skip-criteria list are
  the same rule twice, and they now *disagree* (round-1 defect 5). Merging them fixes the
  contradiction and saves ~3 lines.
- **62-68** — the ASCII workflow block restates the five phase headings verbatim. Cheap navigation,
  but it is the only pure map in the file. ~7 lines, borderline.
- **160-166 (1e) vs 245-248 (3g)** — "Start early, push late" plus the push-gate rationale written in
  both places; 248 is a literal repeat of 161-163's point. Keep 3g's, cut ~2 lines from 1e.
- **192-193** — the two copied `/we:test` rules (round-1 defect 10, still half-open). Replace with the
  citation already sitting on line 190. ~2 lines and one drift surface.
- **13** — "Collects findings from CI + reviews, fixes them, and pushes once everything is addressed"
  is the frontmatter description restated one line below the frontmatter, and 15 restates it again as
  the core principle. Keep 15. ~1 line.
- **237-243 (3f)** — seven lines on merge-vs-rebase and merge-heads placement, which is
  `git-workflow.md` + `stacks/migration-safety.md` territory in the consuming repo. Candidate for a
  two-line citation if those owners exist per project; not a clear cut for a repo-agnostic plugin.

Rough total: ~20 of 285 lines are still duplication, versus round 1's ~70 of 335. The file no longer
carries no-ops; what remains is single-owner debt, and two of those clusters (31/35-38, 190/192-193)
are the residue of round-1 defects that were half-applied.

## Grade

**4/5** — the catastrophic round-1 failure is genuinely gone (1c converts the red check to a row,
consumes the run URL, reads the log, classifies it as the runner, fires the re-run, and 175-176
forbids reporting green), and a fresh Opus agent now lands this scenario correctly with no guessing;
it is not 5 because no phase owns waiting on that re-run or budgets it (N2), 3g's condition (a) is
unsatisfiable for the very disposition 1c just made (N3), Phase 3 still has no empty-diff branch
(round-1 defect 6), and the skill's own fresh-shell warning is violated by its 3d/3e blocks (N1).
