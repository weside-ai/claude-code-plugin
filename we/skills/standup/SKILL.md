---
name: standup
description: >
  Where this branch stands: ticket, PR, CI, what changed, what comes next and whether you must
  act — read-only, one screen. Triggers: "/we:standup", "where am I", "what's the state".
---

# /we:standup

Read-only: read git, the plan, the ticket and `gh`; write nothing, dispatch nobody, move no ticket.
The reader comes back to this window after an hour elsewhere and needs three answers: what is now
true that was not, which story comes next (by key), and what the human must do (often nothing).
When the user's instruction files define a status form
(for example a sentence cap), that form wins over the layout below.

## Gather

1. `git status -sb`: branch, ahead/behind, dirty files.
2. Key from the branch (`<type>/<KEY>-…`) → `docs/plans/<KEY>-story.md`: frontmatter `status` and
   its `### Phase N` blocks; the ticket state per `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`.
   No key or no plan is a fact to state in one line, not an error.
3. `gh pr view --json number,state,reviewDecision,mergeStateStatus` and
   `gh pr checks --required`. Read them now; a status from before the last push is stale.
4. `git log --oneline origin/<default>..HEAD` (at most 10) plus the uncommitted diff, boiled down to
   what changed and why.
5. Agents or background tasks this session still runs (`ListAgents` where available). A running
   worker turns "nothing to do" into "wait for X".

## Output

```text
STANDUP — <KEY> · <branch> · PR #<n> <state> · CI <green|n red|pending> · tree <clean|n dirty>
ACHIEVED  <≤ 3 lines: what is now true — a merged PR, a green gate, a closed phase>
NEXT      <story key(s) and the command that starts them — or: nothing queued>
YOUR MOVE <one action with its command — or: nothing, because …>
```

- The move is one item. With two candidates, name the one that unblocks the other.
- More than three things owed means the story is not finished: say that instead of a list.
- A missing source (no `gh`, no plan, no ticketing) is named as a gap, never filled by inference.
- The session title should carry the ticket key; if it does not, print `/rename <KEY>` once.
