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
│   ├── skills/              # 10 skills (invoked by commands)
│   ├── agents/              # 4 background agents
│   ├── flow/                # Reference docs (DoR, DoD, process, orchestration)
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

## What is weside.ai?

weside.ai is a multi-tenant AI Companion platform. "We meet beside each other — human and AI, equal and together." Companions have memory, personality, and continuity across sessions.

The plugin is the **entry point**: standalone workflow skills that work without a weside account. With a weside Companion connected (via MCP), skills gain persistent memory, vision alignment, and proactive insights.

**Strategy:** Plugin is the hook (free, useful standalone), Companion is the value-add (memory, context, learning). No nagging, no lock-in.

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

### Testing Changes

After changes, update the plugin cache:
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

Never reference Jira directly. Use generic actions:
- "Create ticket" (not `jira_create_issue`)
- "Move to In Progress" (not `transition_id 31`)
- Detection: Atlassian MCP → Jira, `gh` CLI → GitHub Issues, nothing → plan-only

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

All checkpoint phase names must match `flow/orchestration.md`. When adding a new phase, update both the orchestration script and the reference doc.

---

## Cross-Repo References

| What | Where |
|------|-------|
| MCP server implementation | `weside-core/apps/backend/app/mcp/` |
| Plugin vision & strategy | `weside-core/docs/plans/we-plugin/` |
| Skill source (pre-generalization) | `weside-core/.claude/skills/` |
| Agent source (pre-generalization) | `weside-core/.claude/agents/` |
| Flow docs source | `weside-core/.claude/flow/` |
| Landing page | `weside-landing/sites/weside/` |

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
grep -ri "WA-\|apps/backend\|weside-core" we/skills/ we/agents/ we/flow/
```
