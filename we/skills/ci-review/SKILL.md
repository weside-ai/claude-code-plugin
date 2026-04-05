---
name: ci-review
description: >
  CI/Review checker and fixer. Collects ALL findings from CI, Claude Review,
  and CodeRabbit, then fixes everything in a single batch. Runs in the main
  agent (not a subagent) so the user can observe every step.
  Use when user says "/we:ci-review", "fix ci", "fix reviews", "ci failed".
---


# CI Reviewer

Collects findings from CI + reviews, triages, batch-fixes, and pushes — all in one turn.

## Workflow

```
1. Collect (do NOT fix yet)
2. Triage (BLOCKING/WARNING/INFO)
3. Batch Fix (ONE commit)
4. Resolve Threads → Push
5. Report
```

---

## Phase 1: Collect

Detect PR and repo automatically:

```bash
PR=$(gh pr list --head "$(git branch --show-current)" --json number --jq '.[0].number')
REPO=$(gh repo view --json owner,name --jq '"\(.owner.login)/\(.name)"')
```

### 1a. CI Status

```bash
gh pr checks $PR
# If FAILED:
gh run view <run_id> --log-failed 2>&1 | tail -100
```

### 1b. Claude Review

```bash
gh api repos/$REPO/pulls/$PR/reviews \
  --jq '[.[] | select(.user.login=="github-actions[bot]")] | last | .body' 2>/dev/null
```

Parse VERDICT: `VERDICT:PASS`, `VERDICT:WARNING`, `VERDICT:BLOCKING`.

### 1c. CodeRabbit — Two Sources

**Inline threads** (have thread IDs, resolvable):

```bash
gh api graphql -f query='query($pr:Int!,$owner:String!,$repo:String!){
  repository(owner:$owner,name:$repo){
    pullRequest(number:$pr){reviewThreads(first:100){nodes{
      isResolved id comments(first:3){nodes{author{login} body}}
    }}}}}' -F pr=$PR -F owner="$OWNER" -F repo="$REPO"
```

**Review body** (no thread IDs, "outside diff range" issues):

```bash
gh api repos/$REPO/pulls/$PR/reviews \
  --jq '[.[] | select(.user.login=="coderabbitai[bot]")] | last | .body' 2>/dev/null
```

### 1d. Build Findings Table

```
| # | Source | Severity | File:Line | Issue | Thread ID |
```

Severity mapping:
- **BLOCKING** = CI failure, Claude BLOCKING, CodeRabbit CRITICAL/MAJOR
- **WARNING** = Claude WARNING, CodeRabbit MINOR
- **INFO** = CodeRabbit NITPICK, Suggestions

---

## Phase 2: Triage

**0 findings → "Ready for merge" → STOP.**

| Severity | Action |
|----------|--------|
| **BLOCKING** | MUST fix |
| **WARNING** | Fix unless clearly wrong |
| **INFO** | Evaluate. Fix if quick. Skip with reason if not. |

---

## Phase 3: Batch Fix

1. Read each finding, open file, make fix
2. Do NOT commit between fixes
3. After ALL fixes: run local validation (auto-detect stack tools)
4. ONE commit with all fixes:

```bash
git add <specific changed files>
git commit -m "fix: address review findings

{TICKET}"
```

---

## Phase 4: Resolve + Push

### 4a. Resolve ALL CodeRabbit threads

```bash
for id in PRRT_xxx PRRT_yyy; do
  gh api graphql -f query="mutation(\$id:ID!){resolveReviewThread(input:{threadId:\$id}){thread{isResolved}}}" -f id="$id"
done
```

### 4b. Verify zero unresolved

```bash
UNRESOLVED=$(gh api graphql -f query='...' -F pr=$PR -F owner="$OWNER" -F repo="$REPO" \
  --jq '[...select(.isResolved==false)] | length')
```

### 4c. Push ONLY when UNRESOLVED = 0

```bash
git push
```

---

## Phase 5: Report

- Findings table
- Fix summary (1-line per fix)
- Skipped items with reason
- Push status
- "Re-check in ~3 min with /we:ci-review"

---

## Rules

- **NEVER** commit between fixes — all fixes in one commit
- **NEVER** push before resolving threads
- **NEVER** ask "should I fix?" — just fix BLOCKING/WARNING, triage INFO
- **NEVER** ignore review body — it has "outside diff range" findings
- **Max 3 cycles** — after third run still has findings → stop and ask user
- **`--ci-only` flag** — skip reviews, only check CI status
