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
# 1. All three bypass checks must pass
if [ -f scripts/check-primitive-bypass.sh ]; then
    bash scripts/check-primitive-bypass.sh || { echo "FAIL: primitive bypass"; exit 1; }
    bash scripts/check-crud-bypass.sh      || { echo "FAIL: CRUD bypass"; exit 1; }
    bash scripts/check-session-bypass.sh   || { echo "FAIL: session bypass"; exit 1; }
fi

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

### Step 7: Link PR to Ticket

If ticketing tool available → add comment with PR link.

### Step 8: Save Checkpoint

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint $TICKET pr_created
```

---

## Rules

- **VERIFY** all 3 checkpoints before creating PR
- **STOP** if any checkpoint missing
- **ALWAYS** rebase on main before push
- **ALWAYS** save `pr_created` checkpoint after success
- **NEVER** merge PR — that's the user's job
