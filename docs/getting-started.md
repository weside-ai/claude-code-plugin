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
Issues through `gh`, or none), then asks up to five skippable questions: goals, test discipline,
verification, review gates, council. The answers go to `.weside/config.json`. A re-run shows the
current value and asks before replacing it. When a crew works in the repo, setup also writes
`.weside/crew.json` (who is Product Owner, coordinator, HR, Tester, who owns which component) and a
stub role skill per member without one ([workflow.md](workflow.md#crew)). It asks once whether
several people work in the repo, each on their own machine; yes adds the `humans` block
([workflow.md](workflow.md#several-humans)).

Setup also offers the rule bridge for non-Claude agents (when the repo has `.claude/rules/`), the
shipped statusline (model, branch, PR, context, background sessions, cost) and the companion launcher `wclaude`
([companion.md](companion.md#a-companion-session)).

The statusline can also feed claude-swap usage: [Statusline usage feed for claude-swap](#statusline-usage-feed-for-claude-swap).

## First story

1. `/we:epic` — describe the outcome. The skill writes the epic plan with its stories in
   `## Sequencing`.
2. `/we:master <epic>` — the epic's master starts a refiner worker (`/we:plan-story`) that writes the
   story plan at `docs/plans/<KEY>-story.md`, then one `we:dev-medium` worker in its own worktree,
   checks the report against the acceptance criteria and the DoD, pushes once, opens the story's PR
   and runs `/we:ci-review` when CI concludes.
3. `/flow <KEY>` — watch it: a pane with one light per step (plan, approval, build, PR, CI,
   review, merge), refreshed from git and GitHub. Its **Standup** button runs `/we:standup`.
4. Once CI is green and the review checks have their verdict, auto-merge is armed (unless the diff
   falls in the computed one-way class, such as a money path: [who merges what](../we/skills/master/SKILL.md#close-the-run)). Review the PR before it lands if you want to.
5. `/we:merged` — removes the worktrees and branches and moves the ticket to In Review once the PR
   is linked; Done follows acceptance.

## Plugin settings

Every option, its default and the doc that explains it: [docs/README.md § Options](README.md#options).
[companion.md](companion.md) also shows how to start a session as one Companion
(`WESIDE_COMPANION=<Name> claude`).

## Statusline usage feed for claude-swap

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
