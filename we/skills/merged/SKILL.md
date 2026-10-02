---
name: merged
description: >
  Close out a merged PR: verify the merge, tear down its worktrees, branches and processes, move
  the landed tickets to Done, then name only what is still open. Triggers: "/we:merged", "merged",
  "gemergt".
---

# /we:merged — close-out after the merge

1. Confirm `gh pr view <N> --json state` says `MERGED` before deleting anything; `OPEN` or `CLOSED` → report and stop.
2. Tear down only this PR's worktrees, branches and processes; anything foreign or dirty stays and is named.
3. Move every ticket whose work landed in this PR to Done and read the status back.
4. The report lists only what someone still has to do, one line each. It is not a retrospective.
5. Never merge, release, or file a ticket on your own. Follow-ups are named in the report, not created.

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

Run one in the background when the PR needed many review rounds:

- rounds: two or more `fix: address CI and review findings` commits on the PR, or three or more
  completed runs of its required review check (`gh pr view <N> --json commits,statusCheckRollup`);
- covered, and dispatched when not: `${CLAUDE_PLUGIN_ROOT}/skills/retro/SKILL.md` § Auto mode. A retro
  `/we:orchestrate` dispatched for this PR has claimed it, even while it still runs.

Its working directory is the main checkout, never a tree that step 4 removes. Otherwise skip it
silently.

## 4 · Tear down, in this order

1. **Processes.** Find the repo's listening ports with `ss -ltnp`, then check `ls -l /proc/<pid>/cwd` for each candidate.
   A cwd inside a tree you are about to remove, or marked `(deleted)`, is yours: `kill <pid>`.
   A cwd in a foreign tree belongs to another session and stays. Never `pkill -f <pattern>`,
   which matches its own command line and exits 144.
2. **Check each tree:** `git -C <path> status --porcelain`. An untracked `WORKER-REPORT.md` is
   expected. Anything else is unmerged work: leave that tree and name it.
3. **Remove the worktrees**, then `git worktree prune`. A repo with its own worktree-removal verb (one that also
   drops the tree's database fork) uses that verb. That verb also kills a running agent-browser Chrome. If another session is
   driving agent-browser, use `git worktree remove` and name the leftover database fork in the report.
4. **Delete the branches**, local (`git branch -D`) and remote (`git push origin --delete <branch>`).
   `remote ref does not exist` means GitHub already deleted the branch on merge. That counts as success.
5. **Clear the statusline focus** when it names this PR: `rm -f ~/.claude/we-focus/$CLAUDE_CODE_SESSION_ID.json`;
   a stale file keeps a merged PR's number in the statusline.

`--keep-worktrees` skips this whole teardown section.

## 5 · Tickets to Done

Move every story whose work landed in this PR. The branch name alone can miss some, so take the
full list from step 2. A story whose work did not land stays where it is. The human's "merged"
is the word the DoD asks for, so Done is legitimate here.

Ticketing tool, in priority order: weside MCP (`execute_tool` with `JIRA_*`), then Atlassian MCP
(`jira_*`), then `gh issue` (no status, so skip the move), then none (skip silently).

- Find the matching transition. Names vary ("Done", "Fertig", "Erledigt").
- Transition first, comment second, in two calls. A transition's `comment` field wants
  Atlassian Document Format, so prose in it fails the whole transition.
- Read the status back. On a silent failure, retry once with a different transition name. If
  the workflow rejects the move, report it and continue.
- Jira comments are Wiki Markup, not Markdown.

## 6 · Refresh the record

- **Plan:** if `docs/plans/{KEY}-story.md` still describes an intention rather than what was built, correct it.
  The next agent reads the plan, not the diff.
- **Epic mirror:** if the story has an `epic:`, update that story's row in the epic's mirror block
  per `${CLAUDE_PLUGIN_ROOT}/references/apo-hierarchy.md` § Mirror block (status bucket, `Plan` column,
  `updated:`, one `## Updates Log` line), so the next roster does not offer a shipped story again.
- **No state file.** Run state lives in the PR and the ticket, and what is still open lives in
  the report (owner decision 2026-09-25).
- **Repo close-out:** run whatever the repo's `.weside/orchestrate.md` § *Close-out after a merge* names.
- **Where these commits land:** `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md`. Never push a tree that carries another session's unpushed commits.

## 7 · Report what is still open

One line per item, and only what someone has to do:

- rounds a receipt names as owed, such as a live round, a staging round or a device round;
- a deploy or release that the merge does not trigger on its own (`a release <env> <bump>` is the user's word);
- a decision the PR put to the user;
- follow-ups found along the way, named with a recommendation. They are never filed without the user asking;
- trees, branches or processes left standing, and why.

Leave out anything that is merely true: what the PR contained, which gates were green, how many
tests ran. If nothing is open, say so in one line.
