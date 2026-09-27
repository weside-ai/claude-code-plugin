# Getting started

## Install

```text
/plugin marketplace add weside-ai/claude-code-plugin
/plugin install we@weside-ai
```

Requirements: Claude Code, Git, Python 3, and the `gh` CLI for PRs and GitHub Issues.

## Configure the repo

Run `/we:setup` in the repo. It detects the stack from marker files (`pyproject.toml`,
`package.json`, `Cargo.toml`, `go.mod`) and the ticketing tool (Jira through an MCP server, GitHub
Issues through `gh`, or none), then asks up to five skippable questions: vision, test discipline,
verification, review gates, council. The answers go to `.weside/config.json`. A re-run shows the
current value and asks before replacing it.

Setup also offers the rule bridge for non-Claude agents (when the repo has `.claude/rules/`) and the
shipped statusline (model, branch, PR, context, cost).

## First story

1. `/we:story` — describe the change. The skill writes a minimal ticket and a detailed plan at
   `docs/plans/<KEY>-story.md` with acceptance criteria and phases.
2. `/we:orchestrate <KEY>` — the Lead dispatches one `we:dev-medium` worker in its own worktree,
   checks the report against the acceptance criteria and the DoD, pushes once, opens the PR and
   runs `/we:ci-review` when CI concludes.
3. You review and merge the PR.
4. `/we:merged` — removes the worktrees and branches and moves the ticket to Done.

For a change too small for a worker, `/we:orchestrate --solo` builds it in the current session.

## Plugin settings

`/plugin settings we@weside-ai`:

| Setting | Default | Effect |
|---|---|---|
| `companion` | empty | weside Companion name |
| `autoMaterialize` | `false` | loads the Companion at session start |
| `autoStoreConversations` | `false` | stores meaningful turns as Companion memories |
| `loadCouncilFromWeside` | `true` | council members carry linked Companions' identities; `false` keeps every lens generic |

The last three need a weside.ai account: [companion.md](companion.md).
