---
name: ci-review
description: >
  CI/Review checker and fixer. Iteratively collects ALL findings from CI, Claude Review,
  and CodeRabbit, fixes everything, and only pushes when ALL sources are addressed.
  Use when user says "/we:ci-review", "fix ci", "fix reviews", "ci failed".
---


# CI Reviewer

Iteratively collects findings from CI + reviews, fixes ALL of them, and pushes only when everything is addressed. Runs in the main agent (not a subagent) so the user can observe every step.

**Core principle: Fix everything. Push once. No leftovers.**

## Workflow

```
1. Collect iteratively (start with what's available, wait for the rest)
2. Triage (BLOCKING/WARNING/INFO)
3. Fix → Validate → Commit → Resolve Threads → Verify 0 Unresolved → Push
4. Post-Push Check (max 3 cycles)
5. Report
```

---

## Phase 1: Collect (Iterative)

Detect PR and repo automatically:

```bash
PR=$(gh pr list --head "$(git branch --show-current)" --json number --jq '.[0].number')
REPO=$(gh repo view --json owner,name --jq '"\(.owner.login)/\(.name)"')
OWNER=$(echo $REPO | cut -d/ -f1)
REPO_NAME=$(echo $REPO | cut -d/ -f2)
```

### 1a. Start with what's ready

Collect from all sources that have completed. Don't wait for everything — start building the findings table with what's available:

```bash
# CI status
gh pr checks $PR

# Claude Review (may not exist yet if check is pending)
gh pr view $PR --json comments --jq '.comments[] | select(.body | test("VERDICT")) | .body'

# CodeRabbit threads (unresolved only)
gh api graphql -f query='query($pr:Int!,$owner:String!,$repo:String!){
  repository(owner:$owner,name:$repo){
    pullRequest(number:$pr){reviewThreads(first:100){nodes{
      isResolved id comments(first:3){nodes{author{login} body}}
    }}}}}' -F pr=$PR -F owner="$OWNER" -F repo="$REPO_NAME" \
  --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false)'

# CodeRabbit review body (for "outside diff range" findings)
gh api repos/$REPO/pulls/$PR/reviews \
  --jq '[.[] | select(.user.login=="coderabbitai[bot]")] | last | .body'
```

### 1b. If CI is still running

If Backend/other checks are `pending` or `in_progress`, **don't wait** — start fixing findings from reviews that are already available. After fixing, check CI again before pushing.

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
| # | Source | Severity | File:Line | Issue | Thread ID | Action |
```

Severity mapping:
- **BLOCKING** = CI failure, Claude BLOCKING, CodeRabbit CRITICAL/MAJOR
- **WARNING** = Claude WARNING, CodeRabbit MAJOR/MINOR
- **INFO** = CodeRabbit NITPICK, Suggestions

---

## Phase 2: Triage

**0 findings → "All green, ready for merge" → STOP.**

| Severity | Action |
|----------|--------|
| **BLOCKING** | MUST fix. No exceptions. |
| **WARNING** | MUST fix. Only skip if the reviewer is factually wrong (explain why). |
| **INFO** | Fix if quick (<2 min). Skip only if truly stupid or out-of-scope. |

### Skip criteria (strict)

A finding may be skipped ONLY when:
- The reviewer is **factually incorrect** (cite evidence)
- The suggestion would **break existing behavior**
- It's a **pre-existing pattern** that was 1:1 moved (not introduced by this PR) AND fixing it is a separate story's scope

"I don't think it's important" is NOT a valid skip reason.

---

## Phase 3: Fix → Validate → Resolve → Push (single flow, no skipping steps)

⛔ **This is ONE continuous flow. Execute every step in order. Do NOT jump to `git push`.**

### 3a. Batch Fix

1. Read each finding, open file, make fix
2. Do NOT commit between fixes — accumulate ALL changes

### 3b. Local Validation

After ALL fixes — run local validation:

```bash
# Python:
ruff check . --fix && ruff format . && mypy app/
# TypeScript:
yarn lint --fix && yarn typecheck
# Tests:
pytest tests/unit/ tests/integration/ --no-cov -x
# Platform Primitive bypass checks:
for s in scripts/check-primitive-bypass.sh scripts/check-crud-bypass.sh scripts/check-session-bypass.sh; do
  [ -f "$s" ] && bash "$s" || { echo "FAIL: $s"; exit 1; }
done
# Bypass register:
[ -f scripts/generate-bypass-register.sh ] && bash scripts/generate-bypass-register.sh --write
```

### 3c. Commit

ONE commit with all fixes:

```bash
git add <specific changed files>
git commit -m "fix: address CI and review findings

{TICKET}"
```

### 3d. Resolve ALL CodeRabbit Threads (MANDATORY before push)

⛔ **Do NOT skip this step. The `check-coderabbit` gate WILL fail if threads are unresolved.**

For EVERY CodeRabbit thread from the findings table — whether fixed or skipped-with-reason — resolve it:

```bash
# Get all unresolved thread IDs
THREADS=$(gh api graphql -f query='query($pr:Int!,$owner:String!,$repo:String!){
  repository(owner:$owner,name:$repo){pullRequest(number:$pr){
    reviewThreads(first:100){nodes{isResolved id}}
  }}}' -F pr=$PR -F owner="$OWNER" -F repo="$REPO_NAME" \
  --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false) | .id')

# Resolve each one
for id in $THREADS; do
  gh api graphql -f query="mutation(\$id:ID!){resolveReviewThread(input:{threadId:\$id}){thread{isResolved}}}" -f id="$id"
done
```

### 3e. Verify Zero Unresolved (HARD GATE)

```bash
UNRESOLVED=$(gh api graphql -f query='query($pr:Int!,$owner:String!,$repo:String!){
  repository(owner:$owner,name:$repo){pullRequest(number:$pr){
    reviewThreads(first:100){nodes{isResolved}}
  }}}' -F pr=$PR -F owner="$OWNER" -F repo="$REPO_NAME" \
  --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false)] | length')

if [ "$UNRESOLVED" -gt 0 ]; then
  echo "⛔ BLOCKED: $UNRESOLVED unresolved CodeRabbit threads. Resolve them before pushing."
  exit 1
fi
echo "✅ All threads resolved ($UNRESOLVED unresolved)"
```

⛔ **If UNRESOLVED > 0: STOP. Go back to 3d. Do NOT proceed to push.**

### 3f. Push

Only after 3e confirms 0 unresolved:

```bash
git push
```

---

## Phase 4: Post-Push Check

After pushing, CI + reviews will re-run (~3-5 min). If new findings appear:

### Self-loop (max 3 total cycles)

1. Wait for checks to settle (use `gh pr checks $PR` to monitor)
2. Re-collect from all sources
3. If new findings → fix and push again
4. After 3 total cycles → STOP and ask user

**Each cycle should fix MORE findings, not the same ones.** If the same finding appears 3 times, you have a structural problem — stop and escalate.

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

- **NEVER** commit between fixes — all fixes in one commit per cycle
- **NEVER** push before resolving ALL threads
- **NEVER** push if Claude Review WARNINGs are unaddressed
- **NEVER** skip warnings without factual justification
- **NEVER** ignore pre-existing CI failures that block the PR — fix them
- **NEVER** ignore the review body — it has "outside diff range" findings
- **FIX warnings** — they are not optional. The only exception is when the reviewer is factually wrong.
- **FIX INFO items** if they take <2 min. Skip only if truly out-of-scope.
- **Max 3 cycles** — after third push still has findings → stop and ask user
- **`--ci-only` flag** — skip reviews, only check CI status
