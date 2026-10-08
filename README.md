# we — Agentic Product Ownership for Claude Code

`we` is a Claude Code plugin with two halves:

- **APO (Agentic Product Ownership):** four plan altitudes — Vision (PRD), Saga (theme), Epic
  (initiative), Story (feature slice) — each with a Solo verb that writes the document and a
  Council meeting that decomposes it into the next altitude.
- **Build pipeline:** a Lead (`/we:orchestrate`) that refines stories without a plan, dispatches one
  dev worker per story, pushes once, opens one PR and works CI and review findings until green.

You review and merge. Claude never merges; `/we:merged` cleans up after your word.

[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE) · Tour: [plugin.weside.ai/tour](https://plugin.weside.ai/tour/) · Docs: [docs/README.md](docs/README.md)

## Install

```text
/plugin marketplace add weside-ai/claude-code-plugin
/plugin install we@weside-ai
```

Then run `/we:setup` once per repo. It detects stack and ticketing, asks up to five skippable
questions and writes `.weside/config.json`. Details: [docs/getting-started.md](docs/getting-started.md).

Requirements: Claude Code, Git, Python 3.9 or later (the `/usr/bin/python3` that the Xcode Command Line Tools install on macOS is 3.9.6), the `gh` CLI for PRs and GitHub Issues.

## Verbs

**Plan (APO)**

- `/we:vision` — writes or sharpens the PRD at `docs/plans/<vision>/PRD.md`.
- `/we:saga` — status of a theme, refine or create it, or promote an overgrown epic.
- `/we:epic` — status of an initiative from plan and ticket mirror, or refine or create it.
- `/we:story` — one sprint-sized story with a build-ready plan; ticket minimal, plan detailed.
- `/we:meet` — a council meeting at one altitude: validates the artifact and decomposes it.
- `/we:council` — convenes role lenses in a live agent team; the lead writes agreement, tension, recommendation.
- `/we:grill` — asks one question at a time until every branch of a plan is resolved.

**Build**

- `/we:orchestrate` — the Lead: refines what has no plan, dispatches workers for what does, runs CI once on one PR.
- `/we:refine` — writes a build-ready plan without a user in the room; what a dispatched refiner runs.
- `/we:develop` — dev-only worker: implements its chunk, runs local gates, commits, reports.
- `/we:pr` — opens the PR: merges the base, pushes once, writes the body with AC evidence.
- `/we:ci-review` — collects every CI and review finding, fixes by severity, resolves threads, pushes once.
- `/we:ac-review` — checks a branch against its story's acceptance criteria and the DoD.
- `/we:merged` — after your merge: tears down worktrees and branches, moves tickets to Done.

**Around the pipeline**

- `/we:setup` — per-repo configuration, council rosters, rule bridge, statusline.
- `/we:standup` — where this branch stands and whether you must act; read-only.
- `/we:retro` — retrospective on a session or PR cycle; findings go to the optimization inbox.
- `/we:instruction-audit` — audits rules, skills and AGENTS.md against fresh Anthropic sources and a budget gate.
- `/we:optimize` — decides inbox candidates with evidence, applies the approved ones, keeps the ledger.
- `/we:resume` — after a usage-limit stop ("weiter"): resumes open items, workers and CI watches.
- `/we:handoff` — a cross-session restart note under `docs/handoffs/`.
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
