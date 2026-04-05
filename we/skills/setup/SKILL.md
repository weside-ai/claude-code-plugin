---
name: setup
description: >
  Project onboarding — detects stack, ticketing tool, and optionally creates
  project vision, DoR, DoD. Interactive, minimal (3 questions). Use when user
  says "/we:setup", "configure project", "set up workflow".
---


# Project Setup

Interactive project onboarding. Three questions, then done.

---

## When to Use

- First time using `/we:*` skills in a project
- When user wants to customize DoR/DoD/Vision
- When ticketing tool or stack detection needs manual override

---

## Workflow

### Step 1: Auto-Detect

Scan the project to detect:

**Stack:**
- `pyproject.toml` → Python (ruff, mypy, pytest)
- `package.json` → Node.js (eslint, tsc, jest/vitest)
- `Cargo.toml` → Rust
- `go.mod` → Go
- Multiple → Monorepo

**Ticketing Tool (check in order):**
- weside MCP JIRA tools available (`execute_tool` with `JIRA_*`) → Jira via Composio (preferred)
- Atlassian MCP available (`jira_*` tools) → Jira direct (fallback)
- `gh` CLI available → GitHub Issues
- Neither → Plan-only mode

**If weside MCP is connected but Jira tools are missing:** Tell the user:
> "Jira is not connected via your weside Companion. To enable it: go to weside.ai → Integrations → connect Jira, then activate it for your Companion."

**Existing Config:**
- `.weside/` directory exists → already configured
- `CLAUDE.md` exists → read for conventions

### Step 1b: Check Plugin Dependencies

Check if recommended companion plugins are installed. Read `~/.claude/plugins/installed_plugins.json` or check if the skill appears in available skills.

| Plugin | Provides | Used By |
|--------|----------|---------|
| `code-simplifier@claude-plugins-official` | `/simplify` skill | Step 4: Simplify in `/we:story` |
| `security-guidance@claude-plugins-official` | Security hooks during development | `/we:develop` security checks |

If either is missing, inform the user:

> "Recommended plugin not installed: **{plugin-name}**. It provides {what}. Install with: `/install {plugin-name}`"
> "The /we:* pipeline works without it, but {feature} will be skipped."

**Do NOT block.** This is informational only — the pipeline works without these plugins.

### Step 2: Ask 3 Questions

```
1. "Do you have a product vision? (Link, file, or brief description)"
   → If yes: save to .weside/vision.md
   → If no: "No problem — we'll skip vision checks for now."

2. "Which ticketing tool? (Auto-detected: {detected})"
   → Confirm or override
   → If Jira: "What's your project key? (e.g. 'PROJ')"

3. "Stack detected: {detected}. Correct?"
   → Confirm or override
```

### Step 3: Save Configuration

If user provided a vision or wants custom DoR/DoD:

```
.weside/
├── vision.md    # Product vision (optional)
├── dor.md       # Custom DoR overrides (optional)
└── dod.md       # Custom DoD overrides (optional)
```

Otherwise: plugin uses built-in defaults from `quality/dor.md` and `quality/dod.md`.

### Step 4: Confirm

```
Project configured!

Stack: Python + TypeScript (monorepo)
Ticketing: Jira (project: PROJ)
Vision: .weside/vision.md

Ready to go:
  /we:refine  — Create/refine stories
  /we:story   — Implement a story end-to-end
  /we:review  — Code review
```

---

## Training on the Job

Setup is the first touchpoint. Use it to gently explain WHY things matter:

| Question | What the user learns |
|---|---|
| "Do you have a vision?" | Vision helps prioritize — without it, every feature seems equally important |
| "Which ticketing tool?" | Structured backlogs prevent context loss and enable traceability |
| "Custom DoR/DoD?" | Quality gates prevent rework — catching issues early is 10x cheaper |

**Never block.** Every question has a "skip" path. The user can always run `/we:setup` again later.

---

## Rules

- NEVER block on any question — always allow skip/default
- NEVER create .weside/ without user consent
- Auto-detection first, confirmation second
- Three questions maximum
- Works without ANY configuration (defaults for everything)
