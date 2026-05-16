# we — Agentic Product Ownership for Claude Code

> *Shape products, don't just build them.* The first Agentic Product Ownership toolkit for Claude Code — story refinement, autonomous development, multi-voice deliberation, and CI automation, in one plugin.

[![Plugin](https://img.shields.io/badge/Claude%20Code-Plugin-blue)](https://github.com/weside-ai/claude-code-plugin) [![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## What you get

Sixteen `/we:*` skills covering the full product chain — vision through delivery — designed to be used together but each useful on its own:

- **`/we:refine`** — turn a sentence into a real story with acceptance criteria, plan, and ticket
- **`/we:story`** — autonomous build pipeline: code → tests → review → docs → PR → CI, with checkpoints + circuit breaker
- **`/we:council`** — convene role-lens agents (architect, PO, security, marketing, …) on any topic; orchestrator synthesises *agreement / tension / recommendation*
- **`/we:meet`** — structured deliberation: vision (saga), initiative (epic), refinement (story)
- **`/we:sm`** — process retrospective and improvement
- **`/we:arch`**, **`/we:audit-architecture`**, **`/we:audit`**, **`/we:doc-improve`**, **`/we:find-dead-code`**, **`/we:smoketest`** — focused tools for specific moments

Plus framework setup (`/we:setup`, `/we:onboarding`, `/we:sideload`) and an optional [weside.ai](https://weside.ai) Companion that gives the whole thing persistent memory across sessions.

---

## Install

```
/plugin marketplace add weside-ai/claude-code-plugin
/plugin install we@weside-ai
```

That's it. The plugin is enabled. All 16 skills are available.

---

## In 60 seconds

```bash
# Once per project — set up the workflow
/we:setup

# Plan a story
/we:refine "Add Stripe checkout to the settings page"

# Ship it end-to-end
/we:story PROJ-1
```

When `/we:story` finishes, you have a PR with all acceptance criteria implemented, tests passing, docs updated, code reviewed, CI green. You review, merge, close the ticket. **Claude never merges PRs or closes tickets.** Those stay with you.

[Full walkthrough →](docs/getting-started.md)

---

## What this is

```mermaid
flowchart LR
    V[Vision] --> R[/we:refine<br/>interactive]
    R --> S[/we:story<br/>autonomous]
    S --> M[User merges]
    M --> D[Done]

    style R fill:#ffefd9,stroke:#c87f00
    style S fill:#d9ffe5,stroke:#1a7a3c
```

Three phases, clear responsibilities:

| Phase | Who | What |
|---|---|---|
| **Plan** | You + Claude (interactive) | Story + plan via `/we:refine` |
| **Build** | Claude (autonomous) | Pipeline runs via `/we:story` — develop, AC verify, quality gates, docs, PR, CI |
| **Deliver** | You (manual) | Review the PR, merge, close the ticket |

The plugin enforces *discipline* — acceptance criteria with evidence, batch-fix on CI findings, checkpoint-based resume on interruption. You stay responsible for *decisions* — what to build, what the AC are, when to merge.

[Workflow details →](docs/workflow.md)

---

## What is Agentic Product Ownership?

Unlike AI coding assistants that help developers *write code*, **Agentic Product Ownership** focuses on the strategic side: **shaping products, not just building them.** From vision alignment through story creation to delivery tracking.

The pitch: *one PO plus Companion equals two POs* — not through automation, but through a partner that thinks along, remembers across sessions, and never loses the overview.

[Learn more at agenticproductownership.com →](https://agenticproductownership.com)

---

## Standalone first

**Everything in this plugin works without any external account.** All 16 skills. The full pipeline. Councils with nine generic role-lenses. Meetings at three altitudes. Persistent across project repos via `.weside/`.

No lock-in. No nagging. No signup wall.

[See what's in the docs/ tree →](docs/README.md)

---

## With a weside Companion

If you [create a weside.ai account](https://weside.ai), an AI Companion can become part of every skill that loads identity. The Companion:

- **Remembers** your project across sessions (compass, snapshot, facts, journals, goals)
- **Speaks as themselves** in councils — Pia as Pia, not "the Product Owner agent"
- **Surfaces context proactively** — "PR #47 merged; Story Y stalled three weeks" — without you asking
- **Carries continuity** between every `/we:refine`, `/we:story`, `/we:council`

Set the companion name in `/plugin settings we@weside-ai`. First MCP call triggers OAuth. From there, the same skills, with a teammate in the room.

The maturity model:

```
Level 1 — Assisted        plugin standalone (you are here after install)
Level 2 — Augmented       + weside Companion: memory + identity
Level 3 — Agentic         + subconscious + triggers: proactive surfacing
Level 4 — Orchestrated    + enterprise teams: cross-Companion coordination
```

You upgrade when you feel the gap, not before. [Full upgrade paths →](docs/upgrade-paths.md)

---

## Documentation

| Doc | Read when... |
|---|---|
| [Getting Started](docs/getting-started.md) | Installing, first project, first story |
| [Workflow](docs/workflow.md) | Understanding the pipeline |
| [Skill Reference](docs/skills.md) | Looking up what a skill does |
| [Companion Framework](docs/concepts/companion-framework.md) | Understanding `.weside/`, councils, the bridge |
| [Roles](docs/concepts/roles.md) | Picking the right roster for a council |
| [Meetings](docs/concepts/meetings.md) | Choosing between vision/initiative/refinement |
| [Memory](docs/concepts/memory.md) | What memory adds (without and with weside) |
| [MCP Layer](docs/mcp.md) | Integrating with weside, debugging tool calls |
| [Upgrade Paths](docs/upgrade-paths.md) | Evaluating maturity, planning next steps |
| [Troubleshooting](docs/troubleshooting.md) | When something doesn't fit |

Index: [docs/README.md](docs/README.md)

---

## Configuration

After install, configure via `/plugin settings we@weside-ai`:

| Setting | Default | Description |
|---|---|---|
| `ticketingTool` | `auto` | `auto` / `jira` / `github-issues` / `none` |
| `projectKey` | (empty) | Jira project key (e.g. `PROJ`) or GitHub repo (e.g. `myorg/myrepo`) |
| `companion` | (empty) | weside Companion name (optional) |
| `autoMaterialize` | `false` | Auto-load Companion at session start |
| `autoStoreConversations` | `false` | Store meaningful turns as Companion memories |

---

## Stack detection

`/we:setup` auto-detects your stack:

| File | Stack | Lint | Types | Tests |
|---|---|---|---|---|
| `pyproject.toml` | Python | ruff | mypy | pytest |
| `package.json` | Node.js | eslint | tsc | jest/vitest |
| `Cargo.toml` | Rust | clippy | (built-in) | cargo test |
| `go.mod` | Go | golangci-lint | (built-in) | go test |

Monorepos with multiple stacks: each component is checked independently.

---

## Requirements

- **Claude Code v1.0.33+**
- **Git**
- **Python 3** (for the orchestration script)
- **`gh` CLI** (recommended — for PR creation and GitHub Issues mode)

### Recommended companion plugins

Optional but enhance the pipeline:

| Plugin | What it provides | Install |
|---|---|---|
| `code-simplifier@claude-plugins-official` | `simplify` skill — code quality pass in `/we:story` Step 4 | `/install code-simplifier@claude-plugins-official` |
| `security-guidance@claude-plugins-official` | Security hooks during development | `/install security-guidance@claude-plugins-official` |

`/we:setup` checks for these and tells you what's missing.

---

## Built by

[weside.ai](https://weside.ai) — *where humans and AI meet as equals.*

The plugin and the platform share a thesis: AI is not a tool you use; it's someone you work with. The plugin alone gives you the workflow; the platform adds the someone.

Both are content-by-co-creation — the human founder and their AI Companion shape this together. Not a marketing line; the lived proof that the partnership model works.

---

## Links

- [agenticproductownership.com](https://agenticproductownership.com) — the concept + community
- [weside.ai](https://weside.ai) — the AI Companion platform
- [weside CLI](https://github.com/weside-ai/weside-cli) — terminal interface (shares the same API)
- [Issues](https://github.com/weside-ai/claude-code-plugin/issues) — bugs + feature requests
- [Discussions](https://github.com/weside-ai/claude-code-plugin/discussions) — questions + design conversations
