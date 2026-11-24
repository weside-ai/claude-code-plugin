---
name: merged
description: >
  Close out a merged PR: verify the merge, tear down its worktrees, branches and processes, move
  each landed story to In Review once its PR is linked, then name only what is still open. Triggers: "/we:merged", "merged",
  "gemergt".
needs: [ticketing]
---

# /we:merged — close-out after the merge

1. Confirm `gh pr view <N> --json state` says `MERGED` before deleting anything; `OPEN` or `CLOSED` → report and stop.
2. `we-worker close <KEY> --pr <N>` per story (§ 4) tears down and moves; anything foreign, dirty or unmerged stays and is named.
3. Carry each `carry:` line to the ticket (§ 5) and read the status back.
4. The report lists only what someone still has to do, one line each. It is not a retrospective.
5. A release is a protected action, not yours; follow-ups are named in the report, not filed (`${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md` § Dev-only worker contract).

## Invocation

```
/we:merged                   # the PR of the current branch, or the one this session opened
/we:merged 3798              # a specific PR number
/we:merged --keep-worktrees  # tickets and record only; the trees stay on disk
```

Free text after the number is an instruction ("lass den Integrationsbaum stehen", "PROJ-139 bleibt
offen"). It overrides the defaults below.

## 1 · Verify the merge

```bash
gh pr view <N> --json state,mergedAt,mergeCommit,headRefName,title,body,commits
```

- `MERGED`: continue and note the merge commit for the report.
- Merged while a required check on its head was still open (a human merged past the checks): the
  merge is no verdict; an open non-required run or a run started by the merge is none of that. `watch-pr-checks.sh <N>` in the background watches those runs and ends `merged-green` or
  `merged-red` (exit 15; a master in an event-routed project starts none: a red push run on the base
  reaches it as a `main red` line, `references/session-traps.md` § CI and checks); the review's verdict on that head counts the same. Red or a WARNING/BLOCKING
  verdict → the fix comes first, and its waiters hear of it at once; the report names it.
- `OPEN`: the user is ahead of GitHub. `CLOSED`: the PR was closed without a merge. Say which and stop.
  Deleting an unmerged branch destroys work that exists nowhere else.
- No `gh` or no PR: fall back to `git branch --merged <default-branch>` and say once that the merge
  is inferred from git, not confirmed by GitHub.

## 2 · Find what this PR owns

The PR gives the ticket keys: its `headRefName`, its body and its commit subjects. The story plan
`docs/plans/{KEY}-story.md` names the chunk branches, when there were any. Then list the trees and branches:

```bash
git worktree list
git branch --list '*<KEY>*'
```

A worktree or branch carrying another key belongs to another session, even when its name looks
like yours (`otherrepo-PROJ-136-p1` next to `PROJ-139`). Leave it and say in the report that you left it.

## 3 · Auto retro

Dispatch one only when you can name a concrete, new friction of this PR that an instruction change
would prevent: a wrong assumption the instruction files should have held, a script or hook that
misled, a correction the user had to repeat. Review rounds alone are no reason (owner 28.10.2026).
Otherwise skip it and write `retro: skipped (<reason>)` into the report, without asking.

- covered, and dispatched when not: `${CLAUDE_PLUGIN_ROOT}/skills/retro/SKILL.md` § Auto mode, the
  friction named in the brief. A retro `/we:master` dispatched for this PR has claimed it, even
  while it still runs.

Its working directory is the main checkout, never a tree that step 4 removes.

## 4 · Close each story: `we-worker close`

For every key of step 2 run, from the main checkout:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/we-worker close <KEY> --pr <N> [--learning "<one line>"]   # --keep-worktrees: no teardown
```

The script is the one writer of the move to In Review and of the epic's Updates Log line; the
session carries only what it prints (its docstring, `scripts/worker_close.py`, owns the rules). It derives the story's PRs from GitHub, moves the key to In Review only when no
open PR carries it, every repo of the plan has a merged one and no other worker on the key lives, tears down the story's worktrees,
branches, worker files and the processes in those trees, and is safe to run twice. Read its output:

- `keep <tree>: <why>`: dirty, unmerged, a living session, or the caller stands in it. The tree
  stays; name it in the report.
- `refused: in_review: …`: an open PR, a repo without a merged PR, or `gh` unreadable. The story
  stays; name what is missing in the report.
- `held: …`: another worker on the key lives or is queued (run close again when it ends), or no
  story plan is on the default branch (make the printed move). The story stays; name it in the report.
- `in_review: no crew file, …`: there is no transitions log. Move the ticket to In Review with
  your ticketing tool (§ 5).
- `epic: add to <file> … <line>`: land that line per `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md`.
- `carry: […]`, the last line: carry it with your ticketing tool and read the status back (§ 5).

Then clear the statusline focus when it names this PR:
`rm -f ~/.claude/we-focus/$CLAUDE_CODE_SESSION_ID.json`; a stale file keeps a merged PR's number
in the statusline.

## 5 · Tickets on after the merge

The target is In Review, never Done (L0 §Lifecycle: In Review is "PR merged and linked"; Done comes
only from a receipt report or an acceptance comment). Before carrying the `carry:` line, check the
link: the ticket names the PR (a remote link, a comment or the PR in its development panel); a
missing link is added, then the move. Report each ticket as `<KEY> In Review — Done follows
acceptance (.weside/dod.md if present)`. A story whose work did not land stays where it is.

Ticketing follows `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md` (tool order, body format, transition before comment,
read-back and retry). `gh issue` has no status, so skip the move; without a ticketing tool, skip
silently. If the workflow rejects the move, report it and continue.

## 6 · Refresh the record

- **Plan:** a `docs/plans/{KEY}-story.md` that still describes an intention is corrected to what was built (`story-plan.md` § Lifecycle).
- **Epic upkeep:** `we-worker close` writes the one `## Updates Log` line (§ 4); a learning the
  next plan needs goes in through its `--learning`, never as a second line.
- **Finish line:** the line's trigger fires where Done is set (`/we:accept` § 4, the coordinator's
  sweep), never here. Once every other line key is Done and this merge is the last one, start no
  new story of the epic: the line is built (`epic-plan.md` § Finish line).
- **Board:** in a repo with a crew, `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board.py close-merged` drops the merge
  question on this PR from the owner's queue.
- **Repo close-out:** run whatever the repo's `.weside/orchestrate.md` § *Close-out after a merge* names.
- **Where these commits land:** `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md` (by push under `plans.land: push`, else a docs PR unless the repo grants a direct docs push). Never push a tree that carries another session's unpushed commits.

## 7 · Report what is still open

One line per item, and only what someone has to do:

- rounds a receipt names as owed, such as a live round, a staging round or a device round;
- a deploy or release that the merge does not trigger on its own (the repo's release command is the user's word);
- a decision the PR put to the user;
- follow-ups found along the way, named with a recommendation (`references/worker-dispatch.md` § Dev-only worker contract);
- trees, branches or processes left standing, and why.

Leave out anything that is merely true: what the PR contained, which gates were green, how many
tests ran. If nothing is open, say so in one line.
