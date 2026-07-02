---
name: ci-review
description: >
  CI/Review checker and fixer — collects ALL findings from CI + every PR
  review source (reviewer-agnostic), fixes per severity policy, resolves
  all bot threads, pushes only when nothing blocking remains. Use when
  user says "/we:ci-review", "fix ci", "fix reviews", "ci failed".
---


# CI Reviewer

Iteratively collects findings from CI + reviews, fixes ALL of them, and pushes only when everything is addressed. Runs in the main agent (not a subagent) so the user can observe every step.

**Core principle: Fix everything. Push once. No leftovers.**

## Severity policy (applies to EVERY source — reviewer-agnostic)

| Severity | What counts | Policy |
|---|---|---|
| **BLOCKING / ERROR** | CI failure · Claude BLOCKING · any reviewer Critical/Major | **MUST fix.** Only exception: the reviewer is demonstrably factually wrong (cite evidence). |
| **WARNING** | Claude WARNING · any reviewer Minor | **MUST fix.** Same single exception. |
| **SUGGESTION / NITPICK / INFO** | Suggestion · Nitpick · Style | **Should** do it; **may** be consciously skipped — with a short explicit reason in the report. |

"I don't think it's important" is NOT a valid skip reason for BLOCKING/WARNING.
Resolving is mandatory for **every bot-authored thread** you handled — fixed **or**
consciously skipped. It is the central, non-skippable step (the old failure mode was
forgetting it). Human-authored threads are never auto-resolved — surface them to the user.

**Skip criteria (strict) — a finding may be skipped ONLY when:** the reviewer is **factually
incorrect** (cite evidence); the suggestion would **break existing behavior**; or it's a
**pre-existing pattern** that was 1:1 moved (not introduced by this PR) AND fixing it is a
separate story's scope.

**Default to a single pass.** Collect → fix all findings → push, then **stop** and report —
one round is the normal case. Only re-enter the post-push loop (Phase 4) when there is a
**concrete reason** to expect a second round: a fix you are genuinely unsure resolved the
finding, a flaky/environment-dependent check, interdependent findings where fixing one may
surface another, or a **high-stakes PR** (security-sensitive, migration, release-blocking)
where you want to *confirm* green rather than assume it. Absent such a reason, do not sit in a
multi-cycle wait — push once, report the resulting CI state, and let the user decide. The
ability to iterate up to the cycle cap remains; it is opt-in by judgement, not the default.

## Workflow

```
1. Collect iteratively (start with what's available, wait for the rest)
2. Triage (BLOCKING/WARNING/INFO)
3. Fix → Validate → Commit → Resolve Threads → Verify 0 Unresolved → Push
4. Post-Push Check (max 2 cycles)
5. Report
```

---

## Phase 1: Collect (Iterative)

Detect PR and repo. If `gh` is unavailable or unauthenticated, skip GitHub-dependent steps and treat local quality gates as authoritative.

```bash
# Precheck: gh available and authenticated?
GH_AVAILABLE=false
if command -v gh &>/dev/null && gh auth status &>/dev/null 2>&1; then
  GH_AVAILABLE=true
fi

if [ "$GH_AVAILABLE" = true ]; then
  PR=$(gh pr list --head "$(git branch --show-current)" --json number --jq '.[0].number')
  # Derive base branch from remote HEAD rather than assuming 'main'
  BASE=$(gh pr view "$PR" --json baseRefName --jq '.baseRefName' 2>/dev/null \
    || git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' \
    || echo "main")
  REPO=$(gh repo view --json owner,name --jq '"\(.owner.login)/\(.name)"')
  OWNER=$(echo $REPO | cut -d/ -f1)
  REPO_NAME=$(echo $REPO | cut -d/ -f2)
fi
```

### 1a. Start with what's ready

Collect from all sources that have completed. Don't wait for everything — start building the findings table with what's available. Skip GitHub steps when `gh` is unavailable:

There is **ONE** collection path, regardless of which reviewer posted (whatever bots the repo's
`review.available` lists, e.g. CodeRabbit, plus Claude). Do not special-case any reviewer by name.

```bash
if [ "$GH_AVAILABLE" = true ] && [ -n "$PR" ]; then
  # 1) CI status
  gh pr checks $PR

  # 2) PRIMARY — the resolvable unit: ALL unresolved review threads, ANY author.
  #    Each open thread is a finding. author.login tells us bot vs human (see 1d).
  gh api graphql -f query='query($pr:Int!,$owner:String!,$repo:String!){
    repository(owner:$owner,name:$repo){
      pullRequest(number:$pr){reviewThreads(first:100){nodes{
        id isResolved isOutdated
        comments(first:1){nodes{author{login} body path line}}
      }}}}}' -F pr=$PR -F owner="$OWNER" -F repo="$REPO_NAME" \
    --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false)'

  # 3) SECONDARY — context only: latest review body per BOT reviewer, uniform loop
  #    (catches "outside diff range" / summary findings). Bot = login ends in [bot].
  gh api repos/$REPO/pulls/$PR/reviews \
    --jq 'group_by(.user.login)[] | last
          | select(.user.login | endswith("[bot]"))
          | "=== \(.user.login) ===\n\(.body)"'

  # 4) Claude Code Review summary comment — an ISSUE COMMENT, not a review thread,
  #    so steps (2) and (3) above DO NOT catch it. weside's Claude review posts ONE
  #    conversation comment per run as claude[bot]: "## Code Review" with per-finding
  #    <!-- SEV:BLOCKING|WARNING|SUGGESTION --> markers and a final <!-- VERDICT:* -->
  #    line. Take the NEWEST one; every SEV finding in it is a finding for the table.
  #    Because it is a comment, it has NO thread to resolve (see 3d).
  gh api repos/$REPO/issues/$PR/comments --paginate \
    --jq '[.[] | select(.user.login|test("claude";"i")) | select(.body|test("## Code Review"))]
          | sort_by(.created_at) | last | .body // "(no Claude review comment)"'
else
  echo "INFO: gh unavailable or no PR found — skipping remote CI/review collection. Local quality gates are authoritative."
fi
```

### 1b. If CI is still running — start now, but hold the push

If Backend/other checks are `pending` or `in_progress`, **don't wait to START** — collect and fix
findings from the reviews that are already available (Claude Review, CodeRabbit post within a minute
or two; the backend CI can take much longer). Begin triaging and fixing those immediately.

**But gate the PUSH on the long CI concluding.** Before you push (Phase 3f), wait until
`gh pr checks $PR` shows no `pending`/`in_progress` left, then fold any CI failures into the SAME
fix-commit. This ships review-fixes and CI-fixes in one push instead of two, and guarantees the long
CI is actually accounted for. Start early, push late.

### 1c. CI failures: Fix them

**Pre-existing CI failures that block your PR are YOUR problem.** Don't skip them. Common fixes:

| CI Error | Fix |
|----------|-----|
| ImportError (missing native lib) | `pytest.importorskip()` guard |
| Flaky test | Fix or mark `@pytest.mark.flaky` |
| Coverage below threshold | Add tests |
| Lint/type error on unrelated file | Fix it (everyone's responsibility) |

Only skip a CI failure if it's truly unfixable from this branch (e.g., infrastructure issue). Document why.

### 1d. Build Findings Table

```
| # | Source | Bot? | Severity | File:Line | Issue | Thread ID | Action |
```

- **Source** = the reviewer/check that raised it (e.g. CodeRabbit, Claude, CI) —
  derived from `author.login` / check name, never special-cased in logic.
- **Bot?** = yes if the thread's first-comment `author.login` ends in `[bot]` or is in the
  allowlist (`$REVIEW_ALLOWLIST` — union of `review.available`, default `greptile|coderabbit|claude`). Only bot threads get auto-resolved (3d).
  Human threads → mark "needs user confirm", never auto-close.
- **Severity** = read from the thread/body **text** (markers like Critical/Major/Minor/
  Nitpick or 🔴/🟡/🟢 / `VERDICT:`/`SEV:`), per the Severity policy table above — NOT from
  the reviewer's name.
- **Claude Code Review** (source 4) is a summary comment, not threads: split it into one
  row per `<!-- SEV:* -->` finding (BLOCKING/WARNING/SUGGESTION → the policy table). Its
  **Thread ID is "—"** (a comment can't be resolved) and it is **not** subject to the 3e
  thread gate — it is confirmed by the re-review after push (3d note / Phase 4): the next
  run posts a delta with ✅ Fixed and a `VERDICT:PASS`, which is what the CI gate checks.

---

## Phase 2: Triage

**0 findings → "All green, ready for merge" → STOP.**

Otherwise triage every finding per the **Severity policy** table above (the single spec —
BLOCKING/WARNING must fix, SUGGESTION may be consciously skipped with reason).

---

## Phase 3: Fix → Validate → Resolve → Push (single flow, no skipping steps)

⛔ **This is ONE continuous flow. Execute every step in order. Do NOT jump to `git push`.**

### 3a. Batch Fix

1. Read each finding, open file, make fix
2. Do NOT commit between fixes — accumulate ALL changes

### 3b. Local Validation

After ALL fixes — run local validation. **Affected tests only**, not the full suite (CI runs that on push):

```bash
# Determine scope: files changed vs base
BASE_REF=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo "main")
CHANGED=$(git diff --name-only "origin/${BASE_REF}...HEAD" 2>/dev/null)
[ -z "$CHANGED" ] && CHANGED=$(git diff --name-only HEAD~1)

# Detect source root (first of: src/, app/, lib/, or repo root)
SRC_ROOT=$(git rev-parse --show-toplevel)
for candidate in src app lib; do
  if [ -d "${SRC_ROOT}/${candidate}" ]; then SRC_ROOT="${SRC_ROOT}/${candidate}"; break; fi
done

# Python: lint/format/types — if ruff is present
if command -v ruff &>/dev/null; then
  ruff check . --fix && ruff format .
fi
# mypy — detect config and run on detected source root
if command -v mypy &>/dev/null && [ -f mypy.ini -o -f pyproject.toml -o -f setup.cfg ]; then
  mypy "$SRC_ROOT"
fi

# JavaScript/TypeScript: detect package manager and run lint + typecheck
if [ -f package.json ]; then
  if [ -f yarn.lock ] && command -v yarn &>/dev/null; then
    yarn lint --fix && yarn typecheck
  elif [ -f pnpm-lock.yaml ] && command -v pnpm &>/dev/null; then
    pnpm lint --fix && pnpm typecheck
  elif command -v npm &>/dev/null; then
    npm run lint --if-present && npm run typecheck --if-present
  fi
fi

# Tests — only those covering the diff. If CHANGED touches conftest/jest config or >50 files,
# fall back to the full suite (same policy as the test-runner agent).
# Backend (pytest): map <src>/<path>.py → tests/unit/<path> + tests/integration/test_<basename>*.py
#   COVFLAG=; python -c 'import pytest_cov' 2>/dev/null && COVFLAG="--no-cov"
#   pytest <mapped paths> $COVFLAG -x
# Frontend (Jest):
#   yarn test --findRelatedTests <changed .ts/.tsx files>

# Platform Primitive bypass checks (skip silently if scripts are absent):
for s in scripts/check-primitive-bypass.sh scripts/check-crud-bypass.sh scripts/check-session-bypass.sh; do
  [ -f "$s" ] || continue
  bash "$s" || { echo "FAIL: $s"; exit 1; }
done
# Bypass register (weside-specific, skip if absent):
[ -f scripts/generate-bypass-register.sh ] && bash scripts/generate-bypass-register.sh --write
```

The full suite + coverage gate runs in GitHub Actions on push — duplicating it here only burns time. Phase 4 (post-push CI re-collect) catches anything the affected-only run missed.

### 3c. Commit

ONE commit with all fixes:

```bash
git add <specific changed files>
git commit -m "fix: address CI and review findings

{TICKET}"
```

### 3d. Resolve ALL bot review threads (MANDATORY before push)

⛔ **This is the step that used to get forgotten. It is NOT conditional on any specific
reviewer.** Whenever `gh` is available and a PR exists, resolve every **bot-authored**
unresolved thread you handled — fixed **or** consciously skipped-with-reason. Human-authored
threads are left for the user (never auto-resolved).

> **Claude Code Review (source 4) has no thread to resolve** — it's a summary comment, not
> review threads. Don't try to `resolveReviewThread` it (there's nothing to resolve) and
> don't treat its absence from the thread list as "missed". Its findings are confirmed by
> the re-review: after you push the fixes, the Claude review re-runs and posts a delta with
> `✅ Fixed` and `VERDICT:PASS`; the CI gate fails on `VERDICT:BLOCKING`/`VERDICT:WARNING`,
> so a green gate after push is the proof. Other bots' resolvable threads (below) are unchanged.

```bash
# Bot-name allowlist = union of the repo's configured reviewers; fall back to the literal
# default when there is no .weside/config.json review block (back-compat). The [bot] suffix
# below is the real workhorse; this list only catches bots that don't carry the suffix.
REVIEW_ALLOWLIST=$(jq -r '(.review.available // ["greptile","coderabbit","claude"]) | join("|")' .weside/config.json 2>/dev/null || echo "greptile|coderabbit|claude")

if [ "$GH_AVAILABLE" = true ] && [ -n "$PR" ]; then
  # All unresolved thread IDs whose first-comment author is a bot ([bot] suffix or allowlist).
  THREADS=$(gh api graphql -f query='query($pr:Int!,$owner:String!,$repo:String!){
    repository(owner:$owner,name:$repo){pullRequest(number:$pr){
      reviewThreads(first:100){nodes{isResolved id comments(first:1){nodes{author{login}}}}}
    }}}' -F pr=$PR -F owner="$OWNER" -F repo="$REPO_NAME" \
    --jq '.data.repository.pullRequest.reviewThreads.nodes[]
          | select(.isResolved==false)
          | select(.comments.nodes[0].author.login
                   | (endswith("[bot]")) or test("'"$REVIEW_ALLOWLIST"'";"i"))
          | .id')

  for id in $THREADS; do
    gh api graphql -f query="mutation(\$id:ID!){resolveReviewThread(input:{threadId:\$id}){thread{isResolved}}}" -f id="$id"
  done
fi
```

### 3e. Verify zero unresolved bot threads (HARD GATE)

```bash
# Reuse $REVIEW_ALLOWLIST exactly as set in 3d — do NOT redefine it with a different default.

if [ "$GH_AVAILABLE" = true ] && [ -n "$PR" ]; then
  UNRESOLVED=$(gh api graphql -f query='query($pr:Int!,$owner:String!,$repo:String!){
    repository(owner:$owner,name:$repo){pullRequest(number:$pr){
      reviewThreads(first:100){nodes{isResolved comments(first:1){nodes{author{login}}}}}
    }}}' -F pr=$PR -F owner="$OWNER" -F repo="$REPO_NAME" \
    --jq '[.data.repository.pullRequest.reviewThreads.nodes[]
           | select(.isResolved==false)
           | select(.comments.nodes[0].author.login
                    | (endswith("[bot]")) or test("'"$REVIEW_ALLOWLIST"'";"i"))] | length')

  if [ "$UNRESOLVED" -gt 0 ]; then
    echo "⛔ BLOCKED: $UNRESOLVED unresolved bot review thread(s). Resolve them before pushing."
    exit 1
  fi
  echo "All bot threads resolved. (Human threads, if any, are listed in the report for the user.)"
fi
```

⛔ **If UNRESOLVED > 0: STOP. Go back to 3d. Do NOT proceed to push.**
Human-authored threads do not block this gate — list them in the report instead.

### 3e-bis. Migration branches: rebase + re-check alembic heads before push

If the branch adds an Alembic migration, rebase onto `origin/${BASE_REF}` BEFORE the final push and
confirm `alembic heads` resolves to exactly **one** head. Parallel merges to main repeatedly create
multiple heads — rebasing surfaces the drift here (and lets you add a merge-heads migration) instead of
in red CI. If a second head appears, merge it (a `down_revision = (head_a, head_b)` merge migration) and
re-run the check until `alembic heads` == 1.

### 3f. Push (hold until the long CI has concluded)

Push only after: (a) the long CI has a conclusion — `gh pr checks $PR` shows no
`pending`/`in_progress` (per 1b), with any CI failures folded into the fix-commit; (b) 3e confirms 0
unresolved bot threads; and (c) 3e-bis for migration branches. Start early, push late — one push that
carries both review-fixes and CI-fixes.

```bash
git push
```

---

## Phase 4: Post-Push Check (opt-in — only with a reason to expect a second round)

By default, stop after the first push and report (Phase 5). Enter this loop **only** when one of
the single-pass exceptions applies (uncertain fix, flaky/env-dependent check, interdependent
findings, or a high-stakes PR you want to confirm green). When it does not apply, push once and
let the next CI run speak for itself — do not block in a multi-cycle wait.

When you do loop, after pushing CI + reviews re-run (~3-5 min). If new findings appear:

### Self-loop (max 2 total cycles)

1. Wait for checks to settle (use `gh pr checks $PR` to monitor)
2. Re-collect from all sources
3. If new findings → fix and push again
4. After 2 total cycles → STOP and ask user

**Each cycle should fix MORE findings, not the same ones.** If the same finding appears 2 times, you have a structural problem — stop and escalate.

---

## Phase 5: Report

- Complete findings table with Action column (Fixed/Skipped+reason)
- Fix summary (1-line per fix)
- Skipped items with factual justification
- Push status
- CI status (pass/pending/fail)
- Unresolved thread count (must be 0)

---

## Rules

The severity policy and Phases 1–5 above are the spec — reminders:

- **Fix everything, push once, no leftovers** — accumulate all fixes into ONE commit; push only
  after the long CI concluded AND 3e confirms 0 unresolved bot threads.
- **Never auto-resolve a human-authored thread** — surface it to the user.
- **Claude Code Review is a comment, not threads** — collect from issue comments (source 4),
  split per `<!-- SEV:* -->`; nothing to resolve, confirmed by the post-push re-review verdict.
- **One pass by default, max 2 cycles when looping** — re-enter Phase 4 only with a concrete
  reason; after the second push still has findings → stop and ask the user.
- **`--ci-only` flag** — skip reviews, only check CI status.
