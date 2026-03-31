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
