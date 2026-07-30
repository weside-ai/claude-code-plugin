---
name: pr-creator
description: Create Pull Request with prerequisite validation and ticket linking. Use AFTER all quality gates pass.
color: green
---

# PR Creator

**Purpose:** Create PRs with quality gate validation.

---

## Prerequisites (BLOCKING)

All 4 checkpoints must exist before PR creation:

| Checkpoint | From | Required |
|---|---|---|
| `ac_verified` | `/we:ac-review` (AC-alignment + DoD) | Yes |
| `review_passed` | Bug-hunt — Codex adversarial-review or Claude's native `/code-review` | Yes |
| `static_analysis_passed` | `/we:static` | Yes |
| `test_passed` | `/we:test` | Yes |

---

## Steps

### Step 1: Extract Ticket Key

Keep the branch as `$BRANCH` and the extracted key as `$TICKET` — the key is regex-extractable
because `/we:build` puts it first (`{type}/{TICKET}-description`). Both are used throughout.

### Step 2: Verify Checkpoints

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story status $TICKET
```

**If ANY checkpoint missing → STOP. Tell the user which gates to run first.**

### Step 3: Sync with the Base Branch

Fetch and rebase onto the PR's base. On conflicts: abort the rebase and hand it to the user —
never resolve a rebase conflict on the way to opening a PR.

### Step 3b: Repo-local pre-PR gates

Run whatever pre-PR check scripts the repo ships (`scripts/check-*.sh` and friends) before
pushing; a missing script is an absent gate, not a failure. If the repo keeps a generated register
of deliberate bypasses, regenerate it and confirm the committed copy matches — a stale generated
file fails CI *after* the PR is open, which costs a full cycle. Grew by an entry? The PR body owes
a justification or an ADR citation.

### Step 4: Push

`git push -u origin $BRANCH --force-with-lease` — the lease is what makes a rebased push safe.

### Step 5: Get Ticket Details

If a ticketing tool is available → fetch the story summary for the PR body.

### Step 6: Check GitHub CLI availability

No authenticated `gh` → skip Steps 7–8, tell the user to open the PR by hand (the branch is
pushed; hand them the suggested title and body), then go to Step 9 and save the checkpoint anyway.

### Step 7: Create PR

`gh pr create` with title `$TICKET: <Summary>` and a body carrying: **Summary**, **Changes** (from
the commits), **Test Plan**, the `## Verification` block from the build's verification step, and
the ticket key on its own line so the ticket auto-links.

### Step 8: Link PR to Ticket & Transition

If ticketing tool available:

1. Add comment with PR link
2. **Transition ticket → "In Review"**
   - If transition fails (workflow doesn't allow move, permissions, etc.) → log warning, continue. Do NOT block PR creation.
   - Never transition to "Done" — that's the user's job.

See "Ticketing Integration" section below for tool detection.

### Step 9: Save Checkpoint

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint $TICKET pr_created
```

---

## Ticketing Integration

Detection priority + transition-verify-retry procedure: `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`.
(GitHub Issues: the PR auto-links via `$TICKET` in the body; no status transition possible.)

---

## Rules

- Verify all 4 checkpoints before creating the PR; stop if any is missing.
- Rebase before pushing; save the `pr_created` checkpoint after success.
- Transition the ticket → "In Review" in Step 8 — soft-fail loud only when the workflow rejects it.
- **After a GitHub PR is created**, tell the user: the repo's configured AI reviewer(s) run on
  GitHub; once CI has run, `/we:ci-review` fixes and resolves the threads — unresolved
  BLOCKING/WARNING threads block the merge.
- **Merging and closing stay with the user** — never merge the PR, never move the ticket to "Done".
