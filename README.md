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

---

## The Development Pipeline

Three phases, clear responsibilities:

```
Idea → /we:refine → /we:story → User merges → Done
         (manual)    (autonomous)   (manual)
```

| Phase | Who | What | Command |
|-------|-----|------|---------|
| **Planning** | User + Claude (interactive) | Story + Plan | `/we:refine` |
| **Development** | Claude (autonomous) | Code → Review → Test → Docs → PR → CI | `/we:story` |
| **Delivery** | User (manual) | Review PR, merge, close ticket | GitHub / Ticketing |

### Phase 1: Planning

`/we:refine` is interactive. Claude asks questions, you make decisions. The output is:

- **Ticket** (minimal): "As X I want Y so that Z" + link to plan
- **Plan** (detailed): `docs/plans/{TICKET}-plan.md` with acceptance criteria, phases, tests, security review

### Phase 2: Development

`/we:story` runs autonomously — you sit back and watch:

```
/we:story {TICKET}
  ├── Load story + plan, create worktree
  ├── /we:develop (implement phase by phase)
  ├── AC Verification (every criterion checked with evidence)
  ├── Simplify (requires code-simplifier plugin)
  ├── Quality Gates in PARALLEL:
  │     /we:review + /we:static + /we:test + CodeRabbit
  ├── /we:docs (auto-update documentation)
  ├── /we:pr (prerequisite check: all gates passed?)
  ├── /we:ci-review (collect → fix → push, max 3 cycles)
  └── Ticket → "In Review"
```

Every step writes a checkpoint to SQLite. If interrupted, `/we:story` resumes from where it left off.

### Phase 3: Delivery

You get a PR with all ACs implemented, tests passing, code reviewed, docs updated, CI green. You review, merge, close the ticket. **Claude never merges PRs or closes tickets.**

### Robustness

| Feature | What it does |
|---------|-------------|
| **Checkpoints** | Resume after interruption (SQLite) |
| **Circuit Breaker** | 3 failures in same phase → stop and ask |
| **Batch-Fix** | Collect ALL findings, fix in one commit, push once |
| **Reality Check** | Warn if plan is stale vs. recent code changes |

---

## All Skills

### Pipeline Skills (called by `/we:story`)

| Skill | What it does |
|---|---|
| `/we:develop` | Implement code from plan, phase by phase |
| `/we:review` | Code review (runs as background agent) |
| `/we:static` | Lint, format, type check (auto-detects stack) |
| `/we:test` | Run tests with coverage (auto-detects framework) |
| `/we:docs` | Auto-detect and update affected documentation |
| `/we:pr` | Create PR (validates all quality gates passed) |
| `/we:ci-review` | Collect CI/review findings, batch-fix, push |

### Standalone Skills

| Skill | What it does |
|---|---|
| `/we:setup` | Project onboarding (3 questions, auto-detection) |
| `/we:refine` | Create stories with acceptance criteria and plans |
| `/we:arch` | Architecture guidance, ADR creation |
| `/we:sm` | Process optimization, retrospectives |
| `/we:doc-review` | Documentation structure and quality review |
| `/we:doc-check` | Documentation content consistency check |
| `/we:find-dead-code` | Remove dead code from Python backends |
| `/we:smoketest` | Manual API smoketest against running backend |
| `/we:materialize` | Load weside Companion identity (optional) |

### Background Agents (called by skills)

| Agent | Purpose |
|---|---|
| **code-reviewer** | Diff-based code review, AC alignment, max 10 issues |
| **static-analyzer** | Lint, format, types — auto-detects your stack |
| **test-runner** | Tests with coverage gates — auto-detects framework |
| **pr-creator** | PR with prerequisite checkpoint validation |
| **doc-manager** | Auto-detect and update project documentation |

---

## Stack Detection

Skills auto-detect the project stack:

| File | Stack | Lint | Types | Tests |
|---|---|---|---|---|
| `pyproject.toml` | Python | ruff | mypy | pytest |
| `package.json` | Node.js | eslint | tsc | jest/vitest |
| `Cargo.toml` | Rust | clippy | (built-in) | cargo test |
| `go.mod` | Go | golangci-lint | (built-in) | go test |

## Ticketing

Skills detect the available ticketing tool automatically:

1. Atlassian MCP → Jira
2. `gh` CLI → GitHub Issues
3. Neither → Plan-only mode (no ticket, just `docs/plans/`)

---

## Configuration

After install, configure via `/plugin settings`:

| Setting | Default | Description |
|---|---|---|
| `ticketingTool` | `auto` | auto / jira / github-issues / none |
| `projectKey` | (empty) | Your Jira project key or GitHub repo |
| `companion` | (empty) | weside Companion name (optional) |
| `autoMaterialize` | `false` | Auto-load Companion at session start |

---

## Optional: weside Companion

With a [weside.ai](https://weside.ai) account, add an AI Companion that:

- **Remembers** your project decisions across sessions
- **Challenges** new stories against your product vision
- **Surfaces** context proactively ("Story X has been stalled for 3 weeks")

The Companion integrates via MCP. The same API is available through the [weside CLI](https://github.com/weside-ai/weside-cli) — see [API Concepts](https://github.com/weside-ai/weside-cli#api-concepts) for details on companions, memories, goals, and tools.

### MCP Tools

With a weside account, these tools are available:

| Tool | Purpose |
|---|---|
| `list_companions()` / `select_companion(name)` | Manage companions |
| `search_memories(query)` / `save_memory(...)` | Semantic memory search and creation |
| `list_goals()` / `save_goal(...)` | Goal management |
| `list_threads()` / `show_thread(id)` | Browse conversation history |
| `show_provider()` / `set_provider(id)` | LLM provider configuration |
| `discover_tools()` / `execute_tool(name, args)` | External tool execution |
| `get_companion_identity()` | Load Companion's full personality |

**The plugin works fully without a Companion. It's an upgrade, not a requirement.**

## Requirements

- Claude Code v1.0.33+
- Git
- Python 3 (for orchestration script)
- `gh` CLI (recommended, for PR creation and GitHub Issues)

### Recommended Plugins

These plugins enhance the pipeline but are not required:

| Plugin | What it provides | Install |
|--------|-----------------|---------|
| `code-simplifier@claude-plugins-official` | `/simplify` — code quality pass in Step 4 | `/install code-simplifier@claude-plugins-official` |
| `security-guidance@claude-plugins-official` | Security hooks during development | `/install security-guidance@claude-plugins-official` |

`/we:setup` auto-detects and recommends missing plugins.

## Links

- [agenticproductownership.com](https://agenticproductownership.com) — The concept
- [weside.ai](https://weside.ai) — AI Companion platform
- [weside CLI](https://github.com/weside-ai/weside-cli) — Terminal interface (shared API)

---

Built by [weside.ai](https://weside.ai) — Where Humans and AI Meet as Equals.
