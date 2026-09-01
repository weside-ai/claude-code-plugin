---
name: ci-review
description: >
  Collects every CI and PR-review finding, fixes by severity, resolves bot threads, pushes once.
  Triggers: "/we:ci-review", "fix ci", "fix reviews", "ci failed".
---


# CI Reviewer

Collects findings from CI + reviews, fixes them, and pushes once everything is addressed.

**Core principle: Fix everything. Push once. No leftovers.**

## The review gate

The gate is the set of checks the PR's branch protection requires — read it with
`gh pr checks $PR --required`, never from memory (drop the flag to see the advisory checks too).
It is satisfied when **every required check has concluded non-red** and **zero bot review threads
are unresolved**. A red required check that posted no finding is still red: the gate is the
check's conclusion, not the comment — never report green while one is red.

`--ci-only` narrows the run to CI: collect sources 1 and 4 only, skip thread collection and the
3d/3e thread steps, still fix and push. Everything else is unchanged.

## Severity policy (applies to EVERY source — reviewer-agnostic)

| Severity | What counts | Policy |
|---|---|---|
| **BLOCKING / ERROR** | red required check · reviewer BLOCKING/Critical/Major | **MUST fix.** Only exception: the finding is demonstrably factually wrong (cite evidence) or the red is the runner, not the code (see 1c). |
| **WARNING** | reviewer WARNING/Minor | **MUST fix.** Same exceptions. |
| **SUGGESTION / NITPICK / INFO** | Suggestion · Nitpick · Style | **Should** do it; **may** be consciously skipped — with a short explicit reason in the report. |

**Skip criteria (strict) — a finding may be skipped ONLY when:** it is **factually incorrect**
(cite the code that falsifies it); the suggestion would **break existing behavior**; or it is a
**pre-existing pattern** moved 1:1 (not introduced by this PR) AND fixing it is another story's
scope. "I don't think it's important" is not a reason.

Good skip: *"BLOCKING 'no tenant filter' — false: the call site applies `apply_tenant_scope` three
lines up (`service.py:85`), so the query is already scoped."*
Bad skip: *"BLOCKING 'no tenant filter' — the framework handles this."* (asserts, cites nothing).

**A skipped BLOCKING needs a destination on the PR.** Your terminal report is not one: the
reviewer re-runs on the next push, re-posts the same verdict, and the gate stays red forever.
Post the evidence as a PR comment (`gh pr comment $PR --body …`) — for a thread finding, reply
in the thread before resolving it — and say in the report that the gate needs a human override.

**Finish-first before ticketing.** A small finding (≤ ~30 min) on the seam this PR touches gets
FIXED here — "pre-existing" alone is not a deferral. Ticket only what genuinely cannot ride
along: a product decision the user owns, a money-path change, a foreign subsystem redesign, or a
fix that would bury the diff — and name which reason applies.

**One pass by default.** Collect → fix → push → report. Re-enter Phase 4 only with a concrete
reason (a fix you are unsure of, a flaky check, interdependent findings, a high-stakes PR you want
to see green) — **or because the user set a budget** ("bis gemerged, max 3 Runden"): an explicit
user instruction outranks the default, sets the cap, and defines when you may stop.

---

## Phase 1: Collect

### 1a. Resolve the run's state

Each Bash call is a **fresh shell**: nothing survives between blocks, so **prepend this
derivation to every later block that interpolates one of these variables** — the thread blocks in
3d/3e included. An undefined `$REVIEW_ALLOWLIST` matches every login and turns the hard gate into
a deadlock; an undefined `$GH_AVAILABLE` skips the mandatory resolve step in silence.

```bash
gh auth status >/dev/null 2>&1 && GH_AVAILABLE=true || GH_AVAILABLE=false
PR=$(gh pr view --json number --jq .number 2>/dev/null)
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner); OWNER=${REPO%%/*}; REPO_NAME=${REPO#*/}
BASE_REF=$(gh pr view $PR --json baseRefName --jq .baseRefName)   # from the PR, never assumed "main"
# Bot allowlist = the repo's configured reviewers; the literal default is the no-config fallback.
REVIEW_ALLOWLIST=$(jq -r '(.review.available // ["greptile","coderabbit","claude"]) | join("|")' .weside/config.json 2>/dev/null || echo "greptile|coderabbit|claude")
gh pr view $PR --json mergeable,mergeStateStatus,autoMergeRequest,state
```

**No authenticated `gh` or no PR** → skip every GitHub step, treat the local quality gates as
authoritative, and say so once rather than failing silently.

**`mergeable: CONFLICTING` / `mergeStateStatus: DIRTY`** → required checks may never start; a
check pending with no run behind it is a merge conflict, not a slow job, and no wait fixes it.
Note it and **keep collecting** — the reviews that did post are valid findings. The conflict is a
push-time problem: resolve it in 3f by **merging** `origin/$BASE_REF` (not rebasing — a rebase of
pushed commits needs a force-push, which is the user's call), and after that merge **re-collect
Phase 1**, because the merge changes the diff every finding is judged against.

**`UNKNOWN` is not an answer — poll until it is one.** GitHub computes mergeability
asynchronously, so for a few seconds after every push both fields answer `UNKNOWN`. Read that
once and move on, and a conflicted PR passes for clean; the check that exists to catch conflicts
then never runs. Re-poll until it resolves, and if it still will not, report `UNKNOWN` as
`UNKNOWN` rather than as mergeable:

```bash
for i in 1 2 3 4 5; do
  MERGE_STATE=$(gh pr view $PR --json mergeStateStatus --jq .mergeStateStatus)
  [ "$MERGE_STATE" != "UNKNOWN" ] && break
  sleep 5
done
echo "mergeStateStatus: $MERGE_STATE"
```

**`mergeStateStatus: BEHIND`** is not a conflict — the base simply moved. It still blocks the
merge wherever the repo requires the branch to be up to date, and it is invisible in the checks
table, so treat it like a conflict for 3f's purposes: merge `origin/$BASE_REF` in before the
final push. `BLOCKED` means a required check or a required review is missing, which the findings
table already covers — do not merge the base for that one.

### 1b. Collect from every source

There is **ONE** collection path regardless of which bot posted. Do not special-case a reviewer
by name — the repo's `review.available` list seeds the allowlist, nothing else does.

```bash
# 1) CI status — keep the run URL column, 1c consumes it (add --required for the gate alone)
gh pr checks $PR

# 2) PRIMARY — every unresolved review thread, ANY author. Each open thread is a finding.
gh api graphql -f query='query($pr:Int!,$owner:String!,$repo:String!){
  repository(owner:$owner,name:$repo){pullRequest(number:$pr){reviewThreads(first:100){nodes{
    id isResolved isOutdated comments(first:1){nodes{databaseId author{login} body path line}}
  }}}}}' -F pr=$PR -F owner="$OWNER" -F repo="$REPO_NAME" \
  --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false)'

# 3) Latest review body per BOT reviewer (catches "outside diff range" / summary findings)
gh api repos/$REPO/pulls/$PR/reviews \
  --jq 'group_by(.user.login)[] | last | select(.user.login|endswith("[bot]"))
        | "=== \(.user.login) ===\n\(.body)"'

# 4) Review summary ISSUE COMMENTS — sources 2 and 3 do NOT catch these. Any bot may post one
#    (a review action posts under its own app login OR under github-actions[bot]), so filter by
#    SHAPE, not by name: a bot comment carrying a verdict/severity marker. Newest per author.
gh api repos/$REPO/issues/$PR/comments --paginate \
  --jq '[.[] | select(.user.type=="Bot" or (.user.login|endswith("[bot]")))
       | select(.body|test("VERDICT:|SEV:|Code Review"))] | group_by(.user.login)[] | last | .body'
```

### 1c. Every non-pass check is a BLOCKING row

A red check is a finding even when no bot commented on it — the case an empty findings table
hides. For each non-pass check take the run URL from `gh pr checks` and read the failure where it
actually lives:

```bash
gh run view <run-id> --log-failed
```

Then classify from the log, not from the check name:

- **A real finding** (test assertion, lint, type, coverage, a review verdict that never posted) →
  a BLOCKING row; fix it. A pre-existing failure that blocks your PR is yours.
- **The runner, not the code** — checkout/network HTTP errors, an infrastructure timeout, a job
  that errored without producing a verdict → **re-run it** (`gh run rerun <run-id> --failed`);
  do not change code to appease it. A re-run is not a cycle. If it fails the same way twice,
  report it as infrastructure and stop rather than inventing a code fix.
- **Never started** → check merge state (1a) before waiting.

### 1d. Build the findings table

```
| # | Source | Bot? | Severity | File:Line | Issue | Thread ID | Action |
```

- **Source** = the check or reviewer that raised it, derived from the check name / `author.login`.
- **Bot?** = yes if the first comment's `author.login` ends in `[bot]` or matches
  `$REVIEW_ALLOWLIST` (derived in 1a). Only bot threads are auto-resolved.
- **Severity** = read from the finding's **text** (Critical/Major/Minor/Nitpick, 🔴/🟡/🟢,
  `VERDICT:`/`SEV:`) or from the check's conclusion — never from the reviewer's name.
- A summary **comment** (source 4) splits into one row per `SEV:` finding. Its **Thread ID is
  "—"**: a comment cannot be resolved, so it is outside the 3e gate. It is cleared by the
  re-review after the push posting a passing verdict — or, when you skipped it as factually
  wrong, by the PR comment you left (see Severity policy).
- **Surface human-authored threads to the user NOW**, before fixing — one may say the code is
  intentional and make a bot finding moot. Never auto-resolve them.

### 1e. Long checks: start now, hold the push

Reviews post within a minute or two; the test suites take much longer. Start triaging and fixing
immediately, but **gate the push** on the long checks concluding, so review-fixes and CI-fixes
ship in one push. While waiting, use `gh pr checks $PR --watch`. If a check sits pending with no
run started, re-read merge state (1a) instead of waiting further; if it is still pending after
~2× its usual runtime, report that rather than blocking indefinitely.

---

## Phase 2: Triage

Triage every row per the Severity policy above.

**All green → STOP** only when all three hold: every required check concluded non-red, zero
unresolved threads, zero open SEV findings. An empty findings table next to a red check is 1c's
case, not this one.

---

## Phase 3: Fix → Validate → Commit → Resolve → Push

⛔ **ONE continuous flow, in order. Do NOT jump to `git push`.**

### 3a. Fix

Accumulate ALL changes — do not commit between fixes.

### 3b. Validate locally over the changed surface only

Run the repo's static + affected-test gates (`/we:static`, `/we:test` own the procedure) plus any
repo-local gate scripts (`scripts/check-*.sh`, register generators) — absent script, absent gate.
Two rules carry: **derive the base ref** (1a), and **fall back to the full suite** when the diff
crosses test config or exceeds ~50 files. The full suite and the coverage gate run in CI.

### 3c. Commit

ONE commit with all fixes, subject `fix: address CI and review findings`, and the ticket key in
the body when the branch carries one. Verify HEAD moved afterwards. Nothing changed (every finding
skipped, or the red was a re-run) → no commit; continue at 3d.

### 3d. Resolve ALL bot review threads (MANDATORY before push)

Whenever `gh` is available and a PR exists, resolve every **bot-authored** unresolved thread you
handled — fixed **or** consciously skipped. A skipped thread gets the reason as a reply first
(its first comment's `databaseId`, from 1b's query, addresses the replies endpoint):

```bash
gh api repos/$REPO/pulls/$PR/comments/<databaseId>/replies -f body="Skipped: <evidence>"
```

Leave every human thread for the user. Re-derive the 1a variables at the top of this block.

```bash
if [ "$GH_AVAILABLE" = true ] && [ -n "$PR" ]; then
  THREADS=$(gh api graphql -f query='query($pr:Int!,$owner:String!,$repo:String!){
    repository(owner:$owner,name:$repo){pullRequest(number:$pr){
      reviewThreads(first:100){nodes{isResolved id comments(first:1){nodes{author{login}}}}}
    }}}' -F pr=$PR -F owner="$OWNER" -F repo="$REPO_NAME" \
    --jq '.data.repository.pullRequest.reviewThreads.nodes[]
          | select(.isResolved==false)
          | select(.comments.nodes[0].author.login
                   | (endswith("[bot]")) or test("'"$REVIEW_ALLOWLIST"'";"i")) | .id')
  for id in $THREADS; do
    gh api graphql -f query="mutation(\$id:ID!){resolveReviewThread(input:{threadId:\$id}){thread{isResolved}}}" -f id="$id"
  done
fi
```

### 3e. Verify zero unresolved bot threads (HARD GATE)

Re-run the same query with `| length` — re-deriving `$REVIEW_ALLOWLIST` exactly as 1a does — and
`exit 1` while the count is > 0. Human threads do not block this gate; list them in the report.

**The gate covers threads only.** An open BLOCKING/WARNING from a summary comment (Thread ID
"—") is not visible here — check the findings table's Action column before you call it clear.

- [ ] every BLOCKING/WARNING row is Fixed, re-run, or Skipped-with-evidence
- [ ] every skipped BLOCKING has a reply or PR comment carrying the evidence
- [ ] 0 unresolved bot threads
- [ ] human threads surfaced to the user

### 3f. Merge the base in; one migration head

Merge `origin/$BASE_REF` before the final push whenever the PR is conflicted, is `BEHIND`, or adds a
migration, and for a migration branch confirm the heads resolve to exactly one. Resolve merge
conflicts in the code the way you would any conflict; a rebase instead of the merge forces
`--force-with-lease`, which is the user's decision, not yours. If the second head came in from the
base branch, the merge-heads migration belongs **on the base branch**, not as a per-branch patch:
keep your fixes committed but **unpushed**, report the two heads as the blocking question, and
stop at terminal state 3 rather than patching around it.

### 3g. Push

Push only when: (a) every check has concluded and each failure is fixed, re-run, or documented
as skipped;
(b) 3e's checklist is clear; (c) 3f holds for migration branches. Start early, push late.

```bash
git push
```

---

## Phase 4: Post-push check (opt-in, or user-budgeted)

One **cycle** = one push plus the checks and re-reviews it triggers. Default: stop after the
first push and report; when an exception applies, loop at most twice — a user-stated budget
replaces that cap.

Per cycle: wait for the checks to settle (`gh pr checks $PR --watch`), re-collect all sources,
then run Phase 3 again in full — 3d and 3e included, never a bare re-push. **A repeat is the same
finding text on the same `file:line` after a fix aimed at it**; that means the fix is not landing
where the reviewer looks, so stop and escalate. A new finding *caused* by your fix is a new
finding: fix it and continue.

**Terminal states** — every run ends in exactly one, and each is reported:

1. **Green** — gate satisfied, nothing unresolved. If auto-merge is armed
   (`autoMergeRequest != null`) and `mergeStateStatus` is clean, the merge fires without you: say
   so and stop. Only when the user asked for the merge itself ("bis gemerged") confirm it: the
   merge lands a minute or two after the gate goes green, so poll `gh pr view $PR --json
   state,mergedAt` for a few minutes and report `MERGED`, or report green-but-not-yet-merged.
2. **Cap reached, still red** — stop, report what is open and what you tried.
3. **Blocked, nothing to fix** — infrastructure red after a re-run, or a BLOCKING you skipped as
   factually wrong: the PR needs a human. Report it as blocked, do not keep pushing.

**When the user is away**, "ask the user" is not available: take the safest branch, record the
decision and the open question in the report, and stop — never expand the budget on your own.

---

## Phase 5: Report

- Findings table with the Action column (Fixed / Skipped + evidence)
- Fix summary, one line each
- Push status · gate status per required check · terminal state (1, 2 or 3 above)
- **Merge state**, always, in one line: `CLEAN`, `BEHIND`, `DIRTY` (conflicts — name the files),
  `BLOCKED` or an `UNKNOWN` that would not resolve. A green PR that cannot be merged is not a
  finished run, and the user finds out here or at the merge button.
- Unresolved bot threads (must be 0) and every human thread, verbatim, for the user
