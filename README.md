# we — Agentic Product Ownership for Claude Code

`we` is a Claude Code plugin with two halves:

- **Plans:** an epic (one outcome, serving a metric of your goal file) and its stories, each story
  one PR with a build-ready plan. `/we:epic` writes the epic; a refiner worker writes each story plan.
- **Build pipeline:** an epic's master (`/we:master`) that starts a refiner worker for a story without
  a plan and one dev worker per planned story, opens one PR per story and works CI and review
  findings until green.
- **Crew process (optional):** a crew of companions or people — Product Owner, coordinator, HR,
  Tester, component owners — with one master per epic and workers that build. `/we:setup` writes
  the repo's crew; every session then starts with the crew process and its role card.
  [docs/workflow.md](docs/workflow.md#crew)

Claude arms auto-merge once CI and the Codex review are through, unless the diff falls in the computed one-way class (money path, destructive migration, Terraform or secrets, a loosened tenant, auth or trust rule); you merge those. `/we:merged` cleans up afterwards.

`/flow` shows where each story stands while this runs: a pane with one traffic light per pipeline
step, refreshed from git and GitHub, with buttons for the next command.

[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE) · Tour: [plugin.weside.ai/tour](https://plugin.weside.ai/tour/) · Docs: [docs/README.md](docs/README.md)

## Install

```text
/plugin marketplace add weside-ai/claude-code-plugin
/plugin install we@weside-ai
```

Then run `/we:setup` once per repo. It detects stack and ticketing, asks up to five skippable
questions and writes `.weside/config.json`. Details: [docs/getting-started.md](docs/getting-started.md).

Requirements: Claude Code (2.1.302 or later for the `/flow` pane), Git, Python 3.9 or later (the `/usr/bin/python3` that the Xcode Command Line Tools install on macOS is 3.9.6), the `gh` CLI for PRs and GitHub Issues.

## Verbs

**Plan**

- `/we:epic` — status of an epic from plan and ticket mirror, or refine or create it.
- `/we:council` — convenes role lenses in a live agent team; the lead writes agreement, tension, recommendation.
- `/we:grill` — asks one question at a time until every branch of a plan is resolved.

**Build**

- `/we:master` — the epic's master: a refiner worker where a plan is missing, a build worker where one exists, one PR per story.
- `/we:plan-story` — writes a build-ready story plan without a user in the room; what a refiner worker runs.
- `/we:develop` — dev-only worker: implements its chunk, runs local gates, commits, reports.
- `/we:pr` — opens the PR: merges the base, pushes once, writes the body with AC evidence and the net test delta.
- `/we:ci-review` — collects every CI and review finding, fixes by severity, resolves threads, pushes once.
- `/we:ac-review` — checks a branch against its story's acceptance criteria and the DoD.
- `/we:lens` — the lens panel: fresh lens agents judge a plan (`ready`) or a PR diff (`t2`) in parallel; one verdict file per subject, green only with every lens and no standing BLOCKING or WARNING.
- `/we:merged` — after your merge: tears down worktrees and branches, moves each landed story to In Review once its PR is linked; Done follows acceptance.

**Around the pipeline**

- `/flow` — a pane with traffic lights per pipeline step for a story, an epic's stories or this session's work; buttons run the next verb. [docs/flow.md](docs/flow.md)
- `/board` — a pane with the workspace board an orchestrator session keeps in `~/.claude/we-state/board.json`: what waits for the owner, which sessions run and on what, with live and start-mode lamps. [we/docs/board.md](we/docs/board.md)
- `/we:setup` — per-repo configuration, council rosters, rule bridge, statusline.
- `/we:accept` — carries a receipts job's verdict for one release candidate: green stories to Done with a generated comment, walks queued for an acceptance worker, red findings routed to their owner.
- `/we:decide` — escalation as one decision story: both owners' positions and costs, settled by the parties within the SLA, else routed to the escalation role or the human's bundle.
- `/we:standup` — picks you back up: what we work on, where it stands, what you must do next; read-only (`--branch` for the branch view).
- `/we:retro` — retrospective on a session or PR cycle; findings go to the optimization inbox.
- `/we:instruction-audit` — audits rules, skills and AGENTS.md against fresh Anthropic sources and a budget gate.
- `/we:optimize` — decides inbox candidates with evidence, applies the approved ones, keeps the ledger.
- `/we:resume` — after a usage-limit stop ("weiter"): resumes open items, workers and CI watches.
- `/we:pin` — which account bills this master session; `on`/`off` restarts it on a fixed account or on the global login. [docs/companion.md](docs/companion.md)
- `/we:sideload` — works in a neighbour repo from here.
- `/we:find-dead-code` — finds and removes dead code in Python backends.
- `/we:codex-task` — sends one task to Codex; ends with the Codex subscription.
- `/we:materialize` — loads your weside Companion's identity (needs a weside.ai account).

## The effort rule

Workers run on Opus. The default worker is `we:dev-medium`. The Lead picks `we:dev-high` and names
the reason for a promise that must hold across several code paths, for transactions, money or
idempotency, for a fix routing around a fragile path, for a second attempt after a failed worker,
and for plan-writing. Implementation never runs on Sonnet. One implementer per story is the normal
case; parallel workers only for disjoint files with a fixed contract.

The numbers behind this rule: [measured facts](we/AUTHORING.md#measured-facts-a-skill-must-respect-opus-55-bench-2627092026)
in `we/AUTHORING.md`.

## Optional: weside Companion

With a [weside.ai](https://weside.ai) account the plugin connects through the `weside-mcp` server:
council members can carry your Companions' identities, and turns can be stored as Companion
memories. Every verb works without an account. Details: [docs/companion.md](docs/companion.md).

## Links

- [agenticproductownership.com](https://agenticproductownership.com) — the concept
- [Issues](https://github.com/weside-ai/claude-code-plugin/issues)
- [AGENTS.md](AGENTS.md) — developer guide for this repo
