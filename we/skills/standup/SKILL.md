---
name: standup
description: >
  Picks you back up: what we work on, where it stands, what you must do next; read-only.
  Triggers: "/we:standup", "where am I", "status" as the whole message.
---

# /we:standup

Read-only: read git, plans, tickets, `gh` and this session's agents; write nothing, dispatch nobody,
move no ticket. The reader lost the thread and needs, in one screen: what are we working on and why,
where does it stand, what is running, and what must the human do next. Every line names keys and
things a reader can act on; nothing outside the active scope appears. When the user's instruction
files define a status form (a sentence cap, a language), that form wins over the layout below.

## 1 · Scope (first hit wins)

1. A key or slug in the arguments (`/we:standup PROJ-123`). A story key narrows the story table, Running and
   Your moves to that story; its epic and saga appear only in Working on. `--branch` → § 4.
2. The ticket key of the current branch (`<type>/<KEY>-…`).
3. Story keys this conversation dispatched or opened PRs for (only from its own context; a fresh
   session or a subagent skips this step).
4. Active epics (`selected`/`in-progress`), else active sagas (`active`): exactly one → it.
   Several → render no scope: one line each `<slug> · <ticket> · updated <date>`, then
   `/we:standup <KEY>`, and stop. None → § 4.

Walk up from a story: its `epic:` → the epic plan → its `saga:` (omit the saga when `null`). A key
with no epic above it → § 4. Children of an epic: its mirror rows
(`${CLAUDE_PLUGIN_ROOT}/references/apo-hierarchy.md` § Mirror block) ∪ `docs/plans/*-story.md` whose
`epic:` names it (one `rg`) ∪ the keys from step 3. In scope: stories that are Active or In Review
plus those this conversation touched. Backlog, blocked and parked children go into one row of Later / others.
**current** = the story with an open PR or a running worker; with several, the one touched last.

## 2 · Gather (bounded: one call per source, not per story)

- PRs: one `gh pr list --search "<K1> OR <K2> … in:title" --state all --limit 30
  --json number,title,state,headRefName,mergedAt,mergeCommit,mergeStateStatus`, matched to a story
  by its key in the title (a PR whose title lacks the key is not found; name that gap); `gh pr checks <n> --required` only for open PRs, read now
  (a status from before the last push is stale).
- Live: for PRs merged in the last 24 h, `git tag --contains <mergeCommit.oid>`. A prod tag (the
  repo's release pattern from its instruction files) means live; a pre-release tag (`-rc`, `-beta`)
  means staging; another tag family counts only for the story that ships it.
- Plans: frontmatter and `## Open Fork` only; state comes from PRs and tags, not the plan's `status`.
- Tickets: status only, one query for all keys (`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`);
  no ticketing configured → one gap line, no `gh issue` for a non-numeric key.
- Running: this session's agents and background tasks (the harness roster, where present); a
  worker's state is its last message. `git status -sb` when a story in scope is the checked-out branch.
- Owed by the human: this conversation's unanswered asks to the user, the mirror rows'
  Notes column, each plan's `## Open Fork`, the epic's unanswered open questions that name
  the user, and due items in the repo's due-items file when its instruction files name one.

A missing source (no `gh`, no plan, no ticketing) is one named gap line, never filled by inference.

## 3 · Output

Markdown, rendered as tables: the product owner found the text-block layout hard to read (24.10.2026).
Headings and column names follow the user's language; keys, tags and commands stay verbatim.

```markdown
**Working on:** <Saga> › <Epic KEY title> — <what this slice delivers, why now>.
**Current:** <Story KEY title> — <one-line goal>.

| Story | Where | Next step |
|---|---|---|
| <KEY title> | <plan · build · PR #n, CI <state> · merged · staging <tag> · live <tag>> | <one action> |

**Just done (24 h):** <≤ 3 items, comma-separated>.
**Running:** <workers, CI watches, releases in flight — or: nothing>.

**Your moves**

| # | What | Where | Why |
|---|---|---|---|
| 1 | <a go, an upload, a test step, or a decision with the recommended option> | <command, URL, file path, screen> | <what it unblocks; for a decision the reason for the recommendation> |

**Mine next:** <≤ 3, comma-separated; omit in a session that started nothing>.

**Later / others**

| What | Owner |
|---|---|
| <parked, waiting on outside> | <owner> |
```

- "Working on" comes first even when everything is green: the reader needs the context first.
- Your moves: at most five, most-blocking first; a decision names the recommended option in What
  and its reason in Why. More than five: show five and say how many more.
- Later / others: at most three rows; omit the table when empty.
- A cell holds one short phrase; detail that does not fit belongs in the plan, not the standup.

## 4 · Branch view (`--branch`, a key without an epic, or no scope)

`/we:orchestrate`'s user-merge close embeds this view.

```text
STANDUP — <KEY> · <branch> · PR #<n> <state> · CI <green|n red|pending> · tree <clean|n dirty>
ACHIEVED  <≤ 3 lines: what is now true — a merged PR, a green gate, a closed phase>
NEXT      <story key(s) and the command that starts them — or: nothing queued>
YOUR MOVE <one action with its command — or: nothing, because …>
```

Gather for the argument key when one is given (its plan, ticket and PR found by key), else for the
current branch: `git status -sb`, the plan and ticket, the PR and its required checks,
`git log --oneline origin/<default>..HEAD` (at most 10, current branch only). The session title should carry the ticket
key; if it does not, print `/rename <KEY>` once, unless the session is a bound companion session
(`${CLAUDE_PLUGIN_ROOT}/references/companion-session.md` § Name and binding).
