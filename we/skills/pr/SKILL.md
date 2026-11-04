---
name: pr
description: >
  Opens the PR for the current branch: merge the base, push once, body with ticket, AC evidence and
  the plan's verification receipt, PR linked to the ticket. Triggers: "/we:pr", "open the PR".
---

# /we:pr

For a branch built outside `/we:master`; master § Push, PR, CI does the same inside a run.

1. Run the repo's static gates and the affected tests by name first, unless this session already ran them green on
   the current HEAD; red → stop and report.
2. `git fetch && git merge origin/<base>` (never rebase: that needs a force-push, the user's call).
   A conflict goes to the user. Then `git push -u origin <branch>` once.
3. Body in a file, passed as `--body-file` (a `--body "$(…)"` cannot be read by the verification
   hook): summary, the ticket key on its own line, AC → evidence, and a `## Verification` block. A plan
   with that block: splice it with `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pr-body-receipt.py <KEY> <body-in> <body-out>`.
   With `verification.pre_merge_receipt` in `.weside/config.json` it also runs that receipt and writes the
   `receipt green|red|not run on DEV` line under the block; only the script writes it, never by hand.
   No ticket, no plan or no block: write it yourself, `**Oracle:**` cli | ui | substitute with what you
   drove and saw, or `not-observed — <reason>` when nothing beyond tests was observed. A hook refusal for
   a wrong flag or an unreadable file is fixed once; a second refusal is reported verbatim.
   One line `Tests: +N / -M (net ±K)` from `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/test-delta.py origin/<base>`
   (what it counts and skips: its docstring). A refactor (branch `refactor/…`, a Conventional Commit of type
   `refactor`, or a plan that says so) with a positive net appends `— <reason>`. Visibility only, it blocks nothing.
4. `gh pr create --title "<KEY>: <summary>" --body-file <file>`. The user merges whatever is open and not
   a draft (owner, 28.10.2026), so `--draft` only for a PR that must not merge even when green: an open
   product decision, an unmerged dependency, a follow-up that still has to land on the branch, a money
   path awaiting the owner. Never for a review or fix round: a red required check already blocks the
   merge, and the Codex review skips drafts (owner, 30.10.2026). A draft's body starts with one line
   `**Draft:** <reason> — ready when <condition>` (hook `draft_reason_gate.py`); `gh pr ready <PR>` once the
   condition holds, with that line removed. A fix after the merge is a
   follow-up PR from `origin/<base>`, never a push to the merged branch. Ticket: link the PR to it and move
   no status (`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`); In Review follows the merge through
   `/we:merged` (L0 §Lifecycle).
5. Report the URL. Auto-merge is the default: when the base branch requires the Codex check, arm it on a
   ready PR right after create, otherwise `/we:ci-review <PR>` arms it once green. The one merge brake is
   the one-way class (master § Close the run).
   A body with a `receipt red` line is not armed (`automerge_gate.py` refuses): rerun step 3 once the receipt is green.
6. Arm the watcher as a background command: `${CLAUDE_PLUGIN_ROOT}/scripts/watch-pr-checks.sh <PR> --sha <head>
   --until-merged`. Whoever opens a PR watches it until the merge (L0 §Sessions).
