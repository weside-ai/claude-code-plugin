---
name: pr
description: >
  Opens the PR for the current branch: merge the base on a conflict, push once, body with ticket, AC evidence and
  the plan's verification receipt, PR linked to the ticket. Triggers: "/we:pr", "open the PR".
needs: [ticketing]
---

# /we:pr

For a branch built outside `/we:master`; master § Push, PR, CI does the same inside a run.

1. Run the repo's static gates and the affected tests by name first, unless this session already ran them green on
   the current HEAD; red → stop and report.
2. `git fetch`; merge `origin/<base>` only on a conflict (`/we:ci-review` § 3; never rebase: that needs a
   force-push, the user's call). A merge conflict goes to the user. Then `git push -u origin <branch>` once.
3. Body in a file, passed as `--body-file` (a `--body "$(…)"` cannot be read by the verification
   hook): summary, the ticket key on its own line, AC → evidence, and a `## Verification` block. A plan
   with that block: splice it with `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pr-body-receipt.py <KEY> <body-in> <body-out>`.
   With `verification.pre_merge_receipt` in `.weside/config.json` it also runs that receipt and writes the
   `receipt green|red|not run on DEV` line under the block; only the script writes it, never by hand.
   One line `Tests: …` from `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/test-delta.py origin/<base>`, with `--junit <file>`
   when the last local run wrote one (what it counts and marks: its docstring). Each `: say why` mark, and a refactor
   (branch `refactor/…`, a Conventional Commit of type `refactor`, or a plan that says so) that adds more functions than it
   removes, appends `— <reason>`. A signal, it blocks nothing.
   A fast-lane story (no plan file): the block carries its ACs, each with its oracle class, and the
   `**Not proven:**` line; acceptance reads them from the PR body.
   No ticket, no plan or no block: write it yourself, `**Oracle:**` cli | ui | substitute with what you
   drove and saw, or `not-observed — <reason>` when nothing beyond tests was observed. A hook refusal for
   a wrong flag or an unreadable file is fixed once; a second refusal is reported verbatim.
   A process worker (`$WE_WORKER_NAME` set) ends the body with its `Model:` line and its signature line
   (`references/worker-dispatch.md` § Dev-only worker contract).
4. `gh pr create --title "<KEY>: <summary>" --body-file <file>`. The user merges whatever is open and not
   a draft (owner, 28.10.2026), so `--draft` only for a PR that must not merge even when green: an open
   product decision, an unmerged dependency, a follow-up that still has to land on the branch, a money
   path awaiting the owner. Never for a review or fix round: a red required check already blocks the
   merge, and the Codex review skips drafts (owner, 30.10.2026). A draft's body starts with one line
   `**Draft:** <reason> — ready when <condition>` (hook `draft_reason_gate.py`). Once the condition holds,
   `${CLAUDE_PLUGIN_ROOT}/scripts/pr_ready.sh <PR> ready --sha <head>` checks head and conflict first, then removes
   that line and readies the PR; `pr_ready.sh <PR> undo "<reason> — ready when <condition>"` is the way back. A fix after the merge is a
   follow-up PR from `origin/<base>`, never a push to the merged branch. Ticket: link the PR to it and move
   no status (`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`); In Review follows the merge through
   `/we:merged` (L0 §Lifecycle).
5. Report the URL. Under the crew's `merge.armer: workflow` the repo's workflow arms and its own rules
   say when a PR opens as a draft; nobody runs `arm_pr.sh` there. Otherwise, who arms and when: the table in `/we:master` § Close the run (a `T0` or `T2` PR that is not one-way
   is armed with `${CLAUDE_PLUGIN_ROOT}/scripts/arm_pr.sh <PR>` right after create, unless it carries a `plan: waits for …` line; the repo's required checks hold the merge).
6. An event-routed master starts no watcher: it acts on the PR's lines
   (`references/session-traps.md` § CI and checks). Anyone else (a worker, a solo run) arms the watcher as a
   background command: `${CLAUDE_PLUGIN_ROOT}/scripts/watch-pr-checks.sh <PR> --sha <head> --until-merged`. The watch follows L0 §Sessions (a worker until green, its starter until the merge).
   Without auto-merge it prints `waiting … auto-merge off` once at green and watches on to the merge, a push
   included: arming later needs no second watcher.
