---
name: pr-creator
description: Create Pull Request with prerequisite validation and ticket linking. Use AFTER all quality gates pass.
color: green
---

# PR Creator

**Purpose:** Create PRs with quality gate validation.

---

## Prerequisites (BLOCKING)

All 3 checkpoints must exist before PR creation:

| Checkpoint | From | Required |
|---|---|---|
| `review_passed` | `/we:review` | Yes |
| `static_analysis_passed` | `/we:static` | Yes |
| `test_passed` | `/we:test` | Yes |

---

## Steps

### Step 1: Extract Ticket Key

```bash
BRANCH=$(git branch --show-current)
TICKET=$(echo "$BRANCH" | grep -oE '[A-Z]+-[0-9]+')
```

### Step 2: Verify Checkpoints

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story status $TICKET
```

**If ANY checkpoint missing → STOP. Tell user which gates to run first.**

### Step 3: Sync with Main

```bash
git fetch origin main
git rebase origin/main
```

If conflicts → `git rebase --abort` and inform user.

### Step 3b: Platform Primitive Pre-PR Checks (if the project has them)

If the project has Platform Primitive enforcement (detect via
`scripts/check-primitive-bypass.sh` existence), run these gates:

```bash
# 1. All three bypass checks must pass — each is independently guarded
# so a missing script is an absent-gate case, not a blocking failure.
for script in \
    scripts/check-primitive-bypass.sh \
    scripts/check-crud-bypass.sh \
    scripts/check-session-bypass.sh
do
    if [ -f "$script" ]; then
        bash "$script" || { echo "FAIL: $script"; exit 1; }
    fi
done

# 2. Bypass Register diff check vs main
if [ -f docs/architecture/BYPASS-REGISTER.md ] && [ -f scripts/generate-bypass-register.sh ]; then
    # Regenerate and verify it matches what's committed (idempotence)
    bash scripts/generate-bypass-register.sh > /tmp/pr-register.md
    if ! diff -q /tmp/pr-register.md docs/architecture/BYPASS-REGISTER.md > /dev/null; then
        echo "FAIL: BYPASS-REGISTER.md is stale — run 'bash scripts/generate-bypass-register.sh --write' and commit"
        exit 1
    fi
    # Growth check: compare line counts vs main
    BASE_COUNT=$(git show origin/main:docs/architecture/BYPASS-REGISTER.md 2>/dev/null | grep -c "^| \`" || echo 0)
    HEAD_COUNT=$(grep -c "^| \`" docs/architecture/BYPASS-REGISTER.md || echo 0)
    if [ "$HEAD_COUNT" -gt "$BASE_COUNT" ]; then
        DELTA=$((HEAD_COUNT - BASE_COUNT))
        echo ""
        echo "⚠️  BYPASS-REGISTER.md grew by $DELTA entry(s) vs origin/main."
        echo "   The PR description MUST either:"
        echo "   (a) cite an ADR that justifies the new bypass(es), or"
        echo "   (b) explain inline why the bypass is the lesser evil."
        echo ""
        echo "   Verify the PR description before marking this gate as pass."
        # This is a warning, not a hard block — the gh pr create step below
        # prompts the user to include the justification in the body.
    fi
fi
```

### Step 4: Push

```bash
git push -u origin $BRANCH --force-with-lease
```

### Step 5: Get Ticket Details

If ticketing tool available → fetch story summary for PR body.

### Step 6: Create PR

```bash
gh pr create \
  --title "$TICKET: <Summary>" \
  --body "$(cat <<'EOF'
## Summary
<Brief description>

## Changes
- [Key changes from commits]

## Test Plan
- [ ] Tests passing locally
- [ ] CI checks passing

---
$TICKET
EOF
)"
```

### Step 7: Link PR to Ticket & Transition

If ticketing tool available:

1. Add comment with PR link
2. **Transition ticket → "In Review"**
   - If transition fails (workflow doesn't allow move, permissions, etc.) → log warning, continue. Do NOT block PR creation.
   - Never transition to "Done" — that's the user's job.

See "Ticketing Integration" section below for tool detection.

### Step 8: Save Checkpoint

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint $TICKET pr_created
```

---

## Ticketing Integration

Detect available ticketing tool (in priority order):

1. weside MCP (`JIRA_*` Composio tools via `execute_tool`) → Jira (preferred)
2. Atlassian MCP (`jira_*` tools) → Jira (fallback)
3. `gh` CLI → GitHub Issues (PR auto-links via `$TICKET` in body; no status transition possible)
4. Nothing → skip transition silently

---

## Rules

- **VERIFY** all 3 checkpoints before creating PR
- **STOP** if any checkpoint missing
- **ALWAYS** rebase on main before push
- **ALWAYS** save `pr_created` checkpoint after success
- **ALWAYS** transition ticket → "In Review" in Step 7 (soft-fail only)
- **ALWAYS** remind user: *"CodeRabbit will review on GitHub. After CI runs, use `/we:ci-review` to resolve threads — unresolved CRITICAL/MAJOR threads block merge via `check-coderabbit` gate."*
- **NEVER** merge PR — that's the user's job
- **NEVER** transition ticket to "Done" — that's the user's job
