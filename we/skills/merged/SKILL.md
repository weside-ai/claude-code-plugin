---
name: merged
description: >
  Close out a merged PR — verify the merge, tear down its worktrees, branches
  and processes, tickets to Done, refresh the epic mirror and state file, then
  name only what is still open. Use when the user says "/we:merged", "merged",
  "gemergt".
---

# /we:merged — the close-out after a human merged

The human merged; everything mechanical that follows is yours. This is `/we:orchestrate` Step 10
as a standalone skill, so it also serves a `--solo` run, a `/we:pr` that landed, or a branch
somebody merged from the GitHub UI while you were elsewhere.

**The closing report is three lines, not a retrospective.** The user just merged — they want to
know what is still owed, not what happened. Reach for `/we:retro` when the lesson is the point.

## Invocation

```
/we:merged                 # the PR of the current branch, or the one this session opened
/we:merged 3798            # a specific PR number
/we:merged --keep-worktrees  # tickets + state only; leave the trees on disk
```

Free text after the number is an instruction ("… lass den Integrationsbaum stehen", "… PROJ-2139
bleibt offen") — honour it over the defaults below.

## Step M1 — Verify the merge before touching anything

```bash
gh pr view <N> --json state,mergedAt,mergeCommit,headRefName,title
```

**`state` must be `MERGED`.** `CLOSED` is not merged and `OPEN` means the user is ahead of
GitHub — say which one you found and stop; deleting the branch of an unmerged PR destroys work
that exists nowhere else. No `gh`, or no PR at all: fall back to `git branch --merged <default>`
and say once that the merge is inferred from git rather than confirmed by GitHub.

Note the merge commit — the state file and the ticket both want it.

## Step M2 — Find what this run owns

Read the state file (`docs/plans/<key>-state.md`) if there is one: it names the integration
branch, the chunk branches and their worktrees. Without one, derive from git:

```bash
git worktree list
git branch --list 'feat/<KEY>-*'
```

**Only the trees and branches of THIS run.** A worktree whose branch belongs to another key is
another session's, live or not — never remove it, and say in the report that you left it.
`weside-core-PROJ-2136-p1` is not yours because it sits next to yours in the listing.

## Step M3 — Tear down, in this order

1. **Processes first.** A worktree removed under a running server leaves an orphan holding a
   port. `ss -ltnp` for the repo's ports, then `ls -l /proc/<pid>/cwd` per candidate: a cwd
   marked `(deleted)` or pointing into a tree you are about to remove is yours to kill **by
   PID**. A live cwd in a foreign tree belongs to another session — coordinate, never kill.
   Never `pkill -f <pattern>`; it matches its own command line.
2. **Check each tree is clean** — `git -C <path> status --porcelain`. A worker's untracked
   `WORKER-REPORT.md` is expected and not a reason to keep the tree; anything else is unmerged
   work, so leave that tree standing and name it in the report.
3. **Remove the worktrees**, then `git worktree prune`.
4. **Delete the branches, local and remote.** `git push origin --delete` answers
   `remote ref does not exist` for a branch GitHub already deleted on merge — that is success,
   not an error.

## Step M4 — Tickets to Done

Every story that landed in this PR, not just the one in the branch name — the state file's
roster is the list. Transition, then **verify** by reading the status back; a transition that
silently failed is the failure mode this step exists for (`references/ticketing.md`).

Done is legitimate here because the human's "merged" is the word the DoD asks for. A story whose
work did **not** land in this PR stays where it is.

## Step M5 — Refresh the record

- **State file:** one row — merged, the merge commit, what teardown did. Then move anything the
  run still owes into an *Open after the merge* section, because the state file outlives the
  session.
- **Epic mirror:** when the story has an `epic:`, refresh that epic's mirror table with the
  merged PR (`/we:epic`), so the next wave's roster does not re-offer a shipped story.
- **Plan:** if it still describes an intention rather than what was built, correct it now —
  the next agent reads the plan, not the diff.

**Where these commits land is a repo fact** (`.weside/orchestrate.md`), and the main worktree is
shared: `git -C <main-worktree> branch --show-current` immediately before committing there.
Another session may have switched it to its own branch, and a plan commit on a stranger's feature
branch is invisible until their PR merges. Equally, do not push a shared worktree that carries
another session's unpushed commits — commit yours, say it is unpushed, and let them push.

## Step M6 — Say what is still open, briefly

Three to six lines. Only what someone has to **do**:

- rounds a receipt named as owed (a live round, a device round) — these are the usual ones;
- a deploy or release the merge does not perform by itself;
- a decision the PR put to the user;
- a follow-up ticket the run created.

Cut anything that is merely true: what the PR contained, which gates were green, how many tests
ran. If nothing is open, say that in one line — that is the best possible answer and it should
read like one.

## Rules

- **Verify, then delete.** Every teardown step follows a confirmed `MERGED`.
- **Never touch another run's worktree, branch or process**, however similar the name.
- **Never merge, never release.** The human merged; a deploy is their next word, not your
  initiative — offer it in the report if the repo needs one.
- Tickets move only for stories that actually landed in this PR.
