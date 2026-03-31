# we — Agentic Product Ownership for Claude Code

The first **Agentic Product Ownership** toolkit for Claude Code. Covers the full product development chain: from story refinement through development, code review, and CI automation.

## What is Agentic Product Ownership?

Unlike AI coding assistants that help developers write code, Agentic Product Ownership focuses on the strategic side: **shaping products, not just building them.** From vision alignment through story creation to delivery tracking.

[Learn more at agenticproductownership.com](https://agenticproductownership.com)

## Install

```
/plugin marketplace add weside-ai/claude-code-plugin
/plugin install we@weside-ai
```

## Quick Start

```bash
# Set up your project (auto-detects stack + ticketing tool)
/we:setup

# Create a story with implementation plan
/we:refine "Add user authentication"

# Implement it end-to-end (autonomous pipeline)
/we:story PROJ-1
```

## What's Included

### Skills (invoke with `/we:*`)

| Skill | Purpose |
|---|---|
| **refine** | Create stories with Given/When/Then acceptance criteria and implementation plans |
| **story** | Full pipeline: git → develop → review → test → PR → CI fix |
| **develop** | Phase-by-phase implementation with auto-fix and local tests |
| **ci-review** | Collect ALL CI/review findings, batch-fix in one commit |
| **sm** | Process optimization, retrospectives, skill quality |
| **arch** | Architecture guidance, ADR creation |
| **doc-review** | Documentation structure and quality review |
| **doc-check** | Documentation content consistency check |
| **setup** | Project onboarding (3 questions, auto-detection) |
| **materialize** | Load weside Companion identity (optional) |

### Agents (run in background)

| Agent | Purpose |
|---|---|
| **code-reviewer** | Diff-based code review, AC alignment, max 10 issues |
| **static-analyzer** | Lint, format, types — auto-detects your stack |
| **test-runner** | Tests with coverage gates — auto-detects framework |
| **pr-creator** | PR with prerequisite checkpoint validation |

### Infrastructure

- **SQLite orchestration** — Checkpoints, circuit breaker, resume after interruption
- **Stack detection** — Auto-detects Python, Node.js, Rust, Go
- **Ticketing abstraction** — Works with Jira, GitHub Issues, or standalone

## Configuration

After install, configure via `/plugin settings`:

| Setting | Default | Description |
|---|---|---|
| `ticketingTool` | `auto` | auto / jira / github-issues / none |
| `projectKey` | (empty) | Your Jira project key or GitHub repo |
| `companion` | (empty) | weside Companion name (optional) |
| `autoMaterialize` | `false` | Auto-load Companion at session start |

## Optional: weside Companion

With a [weside.ai](https://weside.ai) account, add an AI Companion that:

- **Remembers** your project decisions across sessions
- **Challenges** new stories against your product vision
- **Surfaces** context proactively ("Story X has been stalled for 3 weeks")

The plugin works fully without a Companion. It's an upgrade, not a requirement.

## Requirements

- Claude Code v1.0.33+
- Git
- Python 3 (for orchestration script)
- `gh` CLI (recommended, for PR creation and GitHub Issues)

## Links

- [agenticproductownership.com](https://agenticproductownership.com) — The concept
- [weside.ai](https://weside.ai) — AI Companion platform
- [weside.ai/enterprise](https://weside.ai/enterprise) — Enterprise use cases

---

Built by [weside.ai](https://weside.ai) — Where Humans and AI Meet as Equals.
