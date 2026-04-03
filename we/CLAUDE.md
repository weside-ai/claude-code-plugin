# we — Agentic Product Ownership Toolkit

Development workflow plugin covering the full product chain: story refinement, development orchestration, code review, CI automation, and optional AI companion augmentation.

---

## What is Agentic Product Ownership?

Unlike AI coding assistants that help developers write code, **Agentic Product Ownership** focuses on the strategic side of product development: shaping products, not just building them.

The plugin covers the full upstream chain:

```
Vision → Epic → Story → Development → Review → Done
  PO domain              Dev domain          Delivery
  /we:refine             /we:story           User merges
```

**The pitch:** "One PO plus companion equals two POs — not through automation, but through a companion that thinks along, remembers, and never loses the overview."

Learn more: [agenticproductownership.com](https://agenticproductownership.com)

---

## Pipeline Overview

```
/we:setup    → once per project (detect stack, ticketing, optional vision)
/we:refine   → PO + Claude create story + plan (INTERACTIVE)
/we:story    → Claude runs full pipeline AUTONOMOUSLY:
               develop → AC verify → review + static + test (parallel)
               → docs → PR → CI fix → ticket "In Review"
User         → reviews PR, merges, closes ticket
```

**Full pipeline reference:** `flow/development-process.md`

---

## Skills

| Command | What it does |
|---|---|
| `/we:setup` | Project onboarding (stack, ticketing, vision) |
| `/we:refine` | Create/refine stories with implementation plans |
| `/we:story` | Full autonomous pipeline: git → code → review → PR → CI |
| `/we:develop` | Implement code from a story plan |
| `/we:ci-review` | Collect CI/review findings, batch-fix, push |
| `/we:sm` | Scrum Master: process optimization, retrospectives |
| `/we:arch` | Architecture guidance, ADRs |
| `/we:doc-review` | Documentation structure review |
| `/we:doc-check` | Documentation content consistency check |
| `/we:docs` | Auto-detect and update changed documentation |
| `/we:find-dead-code` | Find and remove dead code from Python backends |
| `/we:materialize` | Load weside Companion identity (requires weside.ai account) |

### Agents (run in background, called by skills)

| Agent | Purpose |
|---|---|
| `code-reviewer` | Diff-based code review, AC alignment, max 10 issues |
| `static-analyzer` | Lint, format, types — auto-detects stack |
| `test-runner` | Tests + coverage — auto-detects framework |
| `pr-creator` | PR with prerequisite checkpoint validation |
| `doc-manager` | Auto-detect and update project documentation |

---

## Typical Workflow

```
/we:setup          (once per project)
/we:refine PROJ-1  (PO creates story + plan)
/we:story PROJ-1   (autonomous: develop → review → test → PR → CI)
```

Or step by step:
```
/we:develop        (implement)
/we:static         (lint/format/types)
/we:test           (run tests)
/we:review         (code review)
/we:pr             (create PR)
/we:ci-review      (fix CI findings)
```

---

## Configuration

Settings via `/plugin settings`:
- **ticketingTool** — auto / jira / github-issues / none
- **projectKey** — Jira project key or GitHub repo
- **companion** — weside Companion name (optional, requires account)
- **autoMaterialize** — Auto-load Companion at session start (default: off)

---

## weside Companion (Optional)

[weside.ai](https://weside.ai) is an AI Companion platform where humans and AI meet as equals. Companions are persons, not tools — with memory, personality, and continuity across sessions.

### What the Companion Adds

| Capability | Without Companion | With Companion |
|---|---|---|
| **Project Memory** | Session-only (.claude/memory/) | Persistent across sessions, accumulates knowledge |
| **Vision Alignment** | Manual or skip | Automatic — Companion Goals = product vision |
| **Context** | User provides each time | Companion remembers decisions, trade-offs, patterns |
| **Proactive Insights** | Never | "PR #47 merged, Story X done, Story Y stalled 3 weeks" |
| **Training on the Job** | Static hints | Companion learns how the PO works, adapts coaching |

### The Maturity Model

```
Level 1: Assisted      Plugin skills work standalone (you are here)
Level 2: Augmented     Companion knows your project context
Level 3: Agentic       Companion acts autonomously (checks, reports, alerts)
Level 4: Orchestrated  Companions coordinate across teams (enterprise)
```

### MCP Tools (with weside account)

| Tool | Purpose |
|---|---|
| `get_companion_identity()` | Load Companion personality |
| `search_memories(query)` | Search project memory |
| `save_memory(title, content, type)` | Save to persistent memory |
| `list_goals()` | Product vision / goals |
| `list_companions()` | Available companions |
| `select_companion(name)` | Switch companion |

**The plugin works fully without a Companion. The Companion is an upgrade, not a requirement. No nagging, no lock-in.**

---

## Stack Detection

Skills auto-detect the project stack:

| File | Stack | Lint | Types | Tests |
|---|---|---|---|---|
| `pyproject.toml` | Python | ruff | mypy | pytest |
| `package.json` | Node.js | eslint | tsc | jest/vitest |
| `Cargo.toml` | Rust | clippy | (built-in) | cargo test |
| `go.mod` | Go | golangci-lint | (built-in) | go test |

Monorepos with multiple stacks are detected and each component is checked independently.

## Ticketing Abstraction

Skills detect the available ticketing tool automatically (in priority order):

1. **weside MCP** (`JIRA_*` Composio tools via `execute_tool`) → Jira (preferred)
2. Atlassian MCP (`jira_*` tools) → Jira (fallback)
3. `gh` CLI → GitHub Issues
4. Neither → Plan-only mode (no ticket, just `docs/plans/`)

**How Composio Jira works:** Tools are called via `execute_tool(name="JIRA_CREATE_ISSUE", arguments='{...}')`. Tool names use `JIRA_` prefix (uppercase). Schemas are self-describing — use `get_tool_schema(name="JIRA_...")` to inspect parameters.

Skills use generic actions ("Create ticket", "Move to In Progress") — never tool-specific API calls. Claude maps generic actions to the best available tool.

---

## References

- **Pipeline:** `flow/development-process.md`
- **DoR/DoD:** `flow/dor.md`, `flow/dod.md`
- **Orchestration:** `flow/orchestration.md` + `scripts/orchestration.py`
- **Epics:** `flow/epic-management.md`
- **Homepage:** [agenticproductownership.com](https://agenticproductownership.com)
- **Platform:** [weside.ai](https://weside.ai)
