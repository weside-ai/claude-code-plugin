# Getting started

## Install

```text
/plugin marketplace add weside-ai/claude-code-plugin
/plugin install we@weside-ai
```

Requirements: Claude Code (2.1.302 or later for the `/flow` pane), Git, Python 3.9 or later, and the `gh` CLI for PRs and GitHub Issues.

## Configure the repo

Run `/we:setup` in the repo. It detects the stack from marker files (`pyproject.toml`,
`package.json`, `Cargo.toml`, `go.mod`) and the ticketing tool (Jira through an MCP server, GitHub
Issues through `gh`, or none), then asks up to five skippable questions: vision, test discipline,
verification, review gates, council. The answers go to `.weside/config.json`. A re-run shows the
current value and asks before replacing it. When a crew works in the repo, setup also writes
`.weside/crew.json` (who is Product Owner, Orchestrator, HR, Tester, who owns which component) and a
stub role skill per member without one ([workflow.md](workflow.md#crew-and-working-mode)).

Setup also offers the rule bridge for non-Claude agents (when the repo has `.claude/rules/`), the
shipped statusline (model, branch, PR, context, background sessions, cost) and the companion launcher `wclaude`
([companion.md](companion.md#a-companion-session)).

If you rotate accounts with [claude-swap](https://github.com/realiti4/claude-swap) and one of them is a
setup-token login whose usage endpoint answers 429, set `WE_CSWAP_FEED_ACCOUNTS` (comma-separated cswap
emails, e.g. in the `env` block of `~/.claude/settings.json`). The statusline then records each
session's `rate_limits` per account in `~/.claude/.we-rate-limits.json` and, at most once a minute,
feeds the listed accounts to `cswap import-usage`. A window whose reset has passed is fed as 0 %,
and every fed row counts as current (`usageAgeSeconds: 0`). That rests on one premise: every use of a
listed account runs in an interactive Claude Code session with this statusline on this machine. List
only such accounts. Headless `claude -p` runs render no statusline, and claude.ai, mobile or another
machine count against the same limits unseen; with those, the feed reports too little and
`cswap auto` may switch to an exhausted account.
Dry run: `node ~/.claude/we-statusline.js --feed-cswap --dry-run`.

## First story

1. `/we:story` — describe the change. The skill writes a minimal ticket and a detailed plan at
   `docs/plans/<KEY>-story.md` with acceptance criteria and phases.
2. `/we:orchestrate <KEY>` — the Lead dispatches one `we:dev-medium` worker in its own worktree,
   checks the report against the acceptance criteria and the DoD, pushes once, opens the PR and
   runs `/we:ci-review` when CI concludes.
3. `/flow <KEY>` — watch it: a pane with one light per step (plan, approval, build, PR, CI,
   review, merge), refreshed from git and GitHub. Its **Standup** button runs `/we:standup`.
4. Once CI and the reviews are green, auto-merge is armed (unless a money path or another exception
   applies; then you merge). Review the PR before it lands if you want to.
5. `/we:merged` — removes the worktrees and branches and moves the ticket to Done (or In Review, per `ticketing.after_merge`).

For a change too small for a worker, `/we:orchestrate --solo` builds it in the current session.

## Plugin settings

Every option, its default and the doc that explains it: [docs/README.md § Options](README.md#options).
[companion.md](companion.md) also shows how to start a session as one Companion
(`WESIDE_COMPANION=<Name> claude`).
