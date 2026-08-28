---
name: pr-creator
description: Create Pull Request with prerequisite validation and ticket linking. Use AFTER all quality gates pass.
color: green
---

# PR Creator

---

## Prerequisites (BLOCKING)

| Checkpoint | Written by | Required |
|---|---|---|
| `ac_verified` | the Lead, after the AC + DoD gate **and** the verification receipt exists | Yes |
| `review_passed` | the Lead, after the one bug-hunt pass | Yes |
| `static_analysis_passed` | the Lead, on `we:static-analyzer`'s report | Yes |
| `test_passed` | the Lead, on `we:test-runner`'s report | Yes |

---

## Steps

### Step 1: Extract Ticket Key

Keep the branch as `$BRANCH` and the key it carries as `$TICKET`; both are used throughout.

### Step 2: Verify Checkpoints

```bash
WE_ROOT=${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/*/we/[0-9]* 2>/dev/null | sort -V | tail -1)}; : "${WE_ROOT:?we plugin root not found}"
python3 "$WE_ROOT/scripts/orchestration.py" story status $TICKET
```

**If any of the four above is missing → STOP. Tell the user which gates to run first.**

### Step 3: Sync with the Base Branch

Fetch and rebase onto the PR's base — **derive it, never assume `main`** (the remote's `HEAD`
symref, or the base the plan names). On conflicts: abort the rebase and hand it to the user —
never resolve a rebase conflict on the way to opening a PR.

### Step 4: Push

`git push -u origin $BRANCH --force-with-lease` — the lease is what makes a rebased push safe.

### Step 5: Get Ticket Details

Fetch the story summary for the PR body when a ticketing tool is available.

### Step 6: Check GitHub CLI availability

No authenticated `gh` → skip Steps 7–8 and hand the user the suggested title and body to open by
hand (the branch is pushed), then Step 9.

### Step 7: Create PR

Write the body to a file and pass it as `--body-file` — a body behind `--body "$(…)"` cannot be
read by the repo's verification gate, which then either blocks a good PR or waves a bad one
through. The body carries: **Summary**, **Changes** (from the commits), **Test Plan**, the ticket
key on its own line so the ticket auto-links, the `## Verification` block **copied verbatim
from `docs/plans/${TICKET}-story.md` § Verification**, and — for any phase committed by
someone other than its worker — who committed it and why.

**Never author that block here.** You did not run the verification, so you cannot testify to it.
No block in the plan → the verification step did not happen: stop, report that, and let the Lead
run it. The same holds if the PR call is refused by a hook for a missing block. A refusal naming a
mechanical fix that authors nothing — a wrong flag, an unreadable body file — you fix once and
retry once; a second refusal is a stop, with its message reported verbatim.

Title: `$TICKET: <Summary>`.

### Step 8: Link PR to Ticket & Transition

If a ticketing tool is available:

1. Add a comment with the PR link
2. **Transition ticket → "In Review"** — a rejected transition (workflow, permissions) is a loud
   warning, not a stop. Never transition to "Done"; that is the user's word after their merge.

Detection priority + transition-verify-retry procedure:
`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`. (GitHub Issues: the PR auto-links via `$TICKET`
in the body; no status transition possible.)

### Step 9: Save Checkpoint

Only once a PR exists — a URL from `gh pr create`, or the user's confirmation that they opened it
by hand. A refused or failed call is not a created PR: report it and write nothing.

```bash
WE_ROOT=${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/*/we/[0-9]* 2>/dev/null | sort -V | tail -1)}; : "${WE_ROOT:?we plugin root not found}"
python3 "$WE_ROOT/scripts/orchestration.py" story checkpoint $TICKET pr_created
```

---

## Rules

- **After a GitHub PR is created**, tell the user: the repo's configured AI reviewer(s) run on
  GitHub; once CI has run, `/we:ci-review` fixes and resolves the threads — unresolved
  BLOCKING/WARNING threads block the merge.
- **Merging stays with the user** — never merge the PR.
