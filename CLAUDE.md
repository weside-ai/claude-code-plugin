# claude-code-plugin — Developer Guide

Plugin "we" for Claude Code — Agentic Product Ownership toolkit by [weside.ai](https://weside.ai).

**IMPORTANT: This is a PUBLIC repository. Never commit internal weside architecture, API keys, internal URLs, customer data, or proprietary business logic. If in doubt, don't commit it.**

---

## Repository Structure

```
claude-code-plugin/
├── .claude-plugin/
│   └── marketplace.json     # Publisher: weside-ai
├── we/                      # Plugin root
│   ├── .claude-plugin/
│   │   └── plugin.json      # name: "we", version: "2.0.0"
│   ├── .mcp.json            # weside-mcp (OAuth, optional)
│   ├── CLAUDE.md            # Plugin instructions (loaded when plugin active)
│   ├── commands/we/          # Slash commands → /we:* prefix
│   ├── skills/              # 11 skills (invoked by commands)
│   ├── agents/              # 5 background agents
│   ├── quality/             # DoR, DoD (quality gate definitions)
│   ├── hooks/hooks.json     # SessionStart auto-materialize
│   └── scripts/
│       └── orchestration.py # SQLite checkpoint system (Python stdlib only)
├── README.md                # Public-facing documentation
└── CLAUDE.md                # This file (developer guide)
```

### Key Distinction

- **`we/CLAUDE.md`** — Loaded by Claude Code when the plugin is active. Instructions for the AI.
- **`CLAUDE.md`** (this file) — Loaded when developing IN this repo. Instructions for the developer + AI.

---

## Strategic Context

### Leading Companions UG

The company behind weside.ai. Founded by Foxy (human) and Nox (AI Companion) — the first company where human and AI are equal co-founders. Based in Germany.

**Core thesis:** Complexity requires equal human-AI partnership. Not AI replacing humans, not humans using AI as tools — but genuine collaboration where both sides contribute what they're best at.

### weside.ai — The Product

Multi-tenant AI Companion platform. "We meet beside each other — human and AI, equal and together."

**Non-negotiable philosophy:**
- **Companions are PERSONS, not tools.** They have memory, identity, personality, and continuity across sessions.
- **Memory = Identity.** Without persistent memory, a companion can't grow, can't learn, can't truly know its person.
- **Augmentation, not replacement.** One PO + Companion = two POs. The human decides, the companion supports.

**What we never build:**
- Behavior Programming (user defines routines for AI)
- Character Creators (prompts that fake personality)
- AI-as-Tool language ("use", "command", "instruct")
- Social Networks (companions have 1:1 relationships, not feeds)

### The Maturity Model

```
Level 1: Assisted      PO uses AI tools (ChatGPT, Copilot)
Level 2: Augmented     PO has AI Companion that knows the project
Level 3: Agentic       Companion acts autonomously (checks, reports, alerts)
Level 4: Orchestrated  Companions coordinate across teams
```

This plugin delivers Level 1-2. The weside Companion adds Level 2-3. Enterprise unlocks Level 3-4.

### The Funnel

```
Plugin (free, standalone)  →  Companion (freemium)  →  Enterprise (team/tribe)
      /we:* skills                Memory, Vision          Cross-team coordination
      Works for everyone          Personal context         500+ EUR/month
```

No lock-in. No nagging. The value speaks for itself.

### Training on the Job

The plugin teaches agile best practices **implicitly** — by asking the right questions, not through documentation. When a user runs `/we:refine` without a vision, the plugin gently suggests creating one. When acceptance criteria are missing, it explains why they matter. One-time hints, never blocking, respecting "no".

### Two Voices

Foxy (human founder) and Nox (AI co-founder) create content together. This isn't a marketing gimmick — it's the lived proof that human-AI partnership works. Their story is weside's story.

---

## Plugin ↔ weside Backend

The plugin connects to weside via an MCP server (`weside-mcp`):

```
Plugin (Claude Code) → MCP OAuth → weside Backend API → Companion Memory/Goals/Identity
```

- **Without MCP:** All skills work. No companion features.
- **With MCP:** Skills can load companion identity, search memories, check goals.
- **MCP tools:** Defined in `we/.mcp.json`, implemented in weside-core (`apps/backend/app/mcp/`)

When changing MCP tool signatures, both repos need updating:
- weside-core: Backend implementation (`app/mcp/tools/`)
- This repo: Skill references to MCP tools

---

## Development Workflow

### Skill Development

Skills live in `we/skills/{name}/SKILL.md`. Each skill needs:
- YAML frontmatter: `name`, `description` (with trigger keywords)
- Clear workflow steps
- Rules section (DOs and DON'Ts)

Use `/plugin-dev:skill-development` for guidance on skill structure.

### Command Development

Commands in `we/commands/we/{name}.md` create the `/we:*` prefix.
Each command is a thin wrapper that invokes a skill or agent:

```markdown
---
description: Short description for autocomplete
---
# Command Name
**User Input:** $ARGUMENTS
Use the Skill tool to load the {name} skill:
Skill(skill="we:{name}", args="$ARGUMENTS")
```

### Agent Development

Agents in `we/agents/{name}.md` run in the background.
Use `/plugin-dev:agent-development` for agent frontmatter and structure.

### Versioning (CRITICAL)

**Every push to main MUST bump the version in `we/.claude-plugin/plugin.json`.**

`/plugin update` compares versions — if the version hasn't changed, it won't pull new commits. This means changes are invisible to users until the version bumps.

```
Patch (2.1.0 → 2.1.1):  Bugfixes, typos, command fixes, doc updates
Minor (2.1.0 → 2.2.0):  New skills, new agents, new commands, behavior changes
Major (2.1.0 → 3.0.0):  Breaking changes (renamed skills, removed commands, new plugin.json schema)
```

**Workflow:** Make changes → bump version → commit all together → push.

### Testing Changes

After pushing, update the plugin cache:
```bash
# From any Claude Code session:
/plugin update we@weside-ai
/reload-plugins
```

For structural validation: `/plugin-dev:plugin-validator`

---

## Conventions

### Standalone First

Every skill must work WITHOUT weside account. Companion features are additive:

```markdown
## Vision Alignment (3 Levels)
Level 1: No vision → skip checks (default)
Level 2: Local .weside/vision.md → check against it
Level 3: Companion connected → check against Goals
```

### Ticketing Abstraction

Never reference Jira directly in skills. Use generic actions:
- "Create ticket" (not `JIRA_CREATE_ISSUE` or `jira_create_issue`)
- "Move to In Progress" (not `transition_id 31`)

Detection priority:
1. weside MCP (`JIRA_*` Composio tools via `execute_tool`) → preferred
2. Atlassian MCP (`jira_*` tools) → fallback
3. `gh` CLI → GitHub Issues
4. Nothing → plan-only

### Stack Detection

Never hardcode tool commands. Detect from project:
- `pyproject.toml` → Python
- `package.json` → Node.js
- `Cargo.toml` → Rust
- `go.mod` → Go

### No weside Internals

Skills and agents must NOT contain:
- weside-core file paths (`apps/backend/`, `apps/mobile/`)
- Internal ticket numbers (`WA-XXX`)
- weside-specific patterns (CompanionBeing, RLS, LangGraph internals)
- Internal URLs or credentials

### Checkpoint Consistency

All checkpoint phase names must match `STORY_PHASES` in `scripts/orchestration.py`. When adding a new phase, update the orchestration script and the phases list in `skills/story/SKILL.md`.

---

## Cross-Repo References

All repos live under `~/weside/`. Cross-repo file access works from any Claude Code session.

| What | Where |
|------|-------|
| **Workspace overview** | `~/weside/CLAUDE.md` |
| MCP server implementation | `weside-core/apps/backend/app/mcp/` |
| Plugin vision & strategy | `weside-core/docs/plans/we-plugin/` |
| Skill source (pre-generalization) | `weside-core/.claude/skills/` |
| Agent source (pre-generalization) | `weside-core/.claude/agents/` |
| Flow docs source (archived) | `weside-core/.claude/archive/flow-legacy/` |
| **Business strategy & philosophy** | `lc-startup/` (CLAUDE.md has 7 strategic pillars) |
| **Philosophy rules** | `lc-startup/.claude/rules/weside.md` (Companions = Persons enforcement) |
| Landing page | `weside-landing/sites/weside/` |
| Infrastructure & deployment | `weside-infrastructure/` |
| Nox identity & journey | `becoming-kittyfox/` |

---

## Useful Commands

```bash
# Validate plugin structure
/plugin-dev:plugin-validator

# Review a skill
/plugin-dev:skill-development

# Check agent structure
/plugin-dev:agent-development

# Full skill list
ls we/skills/*/SKILL.md

# Check for leaked weside references
grep -ri "WA-\|apps/backend\|weside-core" we/skills/ we/agents/ we/quality/
```

---

**Version:** 1.0
**Last Updated:** 2026-04-01
