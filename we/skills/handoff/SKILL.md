---
name: handoff
description: >
  Cross-session restart note: goal, decisions, state, next steps, dead ends in ≤ 2 KB under
  docs/handoffs/; load restores it in that order. Modes --write, default/--load, --list.
  Triggers: "/we:handoff", "handoff", "bis morgen".
---

# /we:handoff

Only for a restart in a new session. Inside one session use the built-ins: `/resume` continues a
session, `/fork` branches one, `/recap` summarises one. A handoff is a file in git that a fresh
session reads first.

| Invocation | Mode |
|---|---|
| `/we:handoff` · `--load <slug>` | load the newest file in `docs/handoffs/`, or the one matching the slug |
| `--list [N]` | date · slug · branch · goal line of the newest N (default 10), frontmatter only |
| `--write [topic]` | write the note now, without a preview or a question |

## Write

Apply `${CLAUDE_PLUGIN_ROOT}/references/privacy-guard.md` to everything taken from the transcript.
File: `docs/handoffs/YYYY-MM-DD-<topic>.md`, topic the most specific slug the session offers. The
body stays under 2048 bytes (`wc -c` after writing; over → cut the least important lines). Most
important first, sections in exactly this order:

```markdown
---
type: handoff
branch: <branch>
last_commit: <git rev-parse --short HEAD>
uncommitted: <n>
written_at: <ISO 8601>
---
## Goal
<the user's goal verbatim, quoted — not paraphrased>
## Decisions
- <decision · who made it · date> — only decisions actually made, never "we discussed"
## Current state
- <done / in progress / blocked, with PR numbers, SHAs and file paths>
## Next steps
1. <the one move to make first, with its command>
## Dead ends
- <approach · why it failed · what would justify a retry>
```

An empty section gets `—`, never filler. Commit it per `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md`; no branch or PR per handoff unless the repo demands PRs for docs.
Then report the path, the byte count and a two-line summary of the decisions and the next step.

## Load

Read the file and restate it in its order: goal, decisions, state, next steps, dead ends. Then
check staleness and say what differs, without blocking: `git rev-parse --short HEAD` against
`last_commit` (commits since), the current branch against `branch`, `git status --short` against
`uncommitted`. Continue with the first next step unless the user redirects; decisions in the file
are not reopened without a new reason.
