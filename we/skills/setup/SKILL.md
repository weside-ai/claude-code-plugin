---
name: setup
description: >
  Project onboarding — detects stack, ticketing tool, creates project vision/DoR/DoD,
  initializes the Companion Framework (`.weside/`, vault registration, crew onboarding
  via /we:onboarding). Interactive, minimal (3 core questions + optional crew setup).
  Use when user says "/we:setup", "configure project", "set up workflow", "initialize repo",
  "install crew", "first time".
---


# Project Setup

Interactive project onboarding. Three core questions for project config, then optional Companion Framework initialization (crew + TurboVault + frontmatter).

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

### Step 1b: Check Plugin Prerequisites

This is the **canonical prerequisite gate** for the `/we:*` pipeline. Verify each prerequisite empirically — never derive availability from plugin filesystem paths alone, since plugins can ship agents, skills, or commands under different names than expected.

**Detection rule:** for each row, run the listed *Detection check*. The check is the source of truth. If it succeeds → prerequisite is met. If it errors with "not found" → mark as missing and inform the user (do NOT block).

| Prerequisite | Detection check | Provided by | Used by |
|---|---|---|---|
| `gh` CLI authenticated | `gh auth status` exits 0 | GitHub CLI install + `gh auth login` | `/we:pr`, `/we:ci-review`, `/we:story` PR creation, CI status, CodeRabbit thread resolution |
| Jira access (one of) | weside MCP Composio `JIRA_*` via `execute_tool` (preferred) / `mcp__atlassian__jira_*` (fallback) / `gh issue` for GitHub-Issues mode | weside MCP + Composio Jira, or Atlassian MCP, or GitHub CLI | `/we:refine`, `/we:story` ticket fetch and transitions |
| `simplify` skill | `Skill(skill="simplify")` available in the skill list | `code-simplifier@claude-plugins-official` (ships an agent that the harness exposes as the `simplify` skill) | `/we:story` Step 4: Simplify |
| security guidance hooks | `security-guidance` plugin in `~/.claude/plugins/installed_plugins.json` | `security-guidance@claude-plugins-official` | `/we:story` Step 2 security checks |
| TurboVault MCP | `mcp__turbovault__*` tools available | TurboVault MCP server | `/we:refine` (semantic search), `/we:story` (architecture context), `/we:docs`, `/we:doc-improve` (skills have fallbacks if missing) |
| weside MCP | `mcp__plugin_we_weside-mcp__get_companion_identity` available | weside MCP (requires weside.ai account) | `/we:materialize`, optional companion memory in `/we:refine` and `/we:story` |

If a prerequisite is missing, inform the user:

> "Recommended plugin not installed: **{plugin-name}**. It provides {what}. Install with: `/install {plugin-name}`"
> "The /we:* pipeline works without it, but {feature} will be skipped."

**Do NOT block.** This is informational — the pipeline works without these plugins. Downstream skills (e.g. `/we:story` Step 4) MUST trust this gate: they invoke the prerequisite directly and only skip when the actual tool call returns "not found", never on assumption.

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

Always write `.weside/config.json` with the choices from Step 2 — the ticketing and stack configuration must persist **even if the Companion Framework (Step 5) is declined**:

```json
{
  "ticketing": { "tool": "<jira|github-issues|none>", "project_key": "<KEY-or-null>" },
  "stack": ["<detected stacks>"]
}
```

If Step 5 runs later, it *extends* this same file (adding `vault`, `council`, `onboarded`, …) rather than replacing it.

If the user provided a vision or wants custom DoR/DoD:

```
.weside/
├── vision.md    # Product vision (optional)
├── dor.md       # Custom DoR overrides (optional)
└── dod.md       # Custom DoD overrides (optional)
```

Otherwise: plugin uses built-in defaults from `quality/dor.md` and `quality/dod.md`.

### Step 4: Confirm core config

```
Project configured!

Stack: Python + TypeScript (monorepo)
Ticketing: Jira (project: PROJ)
Vision: .weside/vision.md
```

### Step 5: Companion Framework Setup (optional — ask first!)

Ask: *"Set up the Companion Framework for this repo now? It composes a crew, registers a TurboVault, and — with a weside account — turns your Companions into a council you can convene via `/we:council` and `/we:meet`. You can also run `/we:onboarding` later."*

If **no** → skip to Step 6.

If **yes** — this step is **idempotent**: if `.weside/config.json` already exists, report the current state (vault, crew, `onboarded_at`) and ask before overwriting anything.

1. **Ensure `.weside/config.json`** — create or extend. Schema:

   ```json
   {
     "vault": "<repo-basename>",
     "onboarded": false,
     "created_at": "<ISO-timestamp>",
     "framework_version": 1,
     "ticketing": { "tool": "<jira|github-issues|none>", "project_key": "<KEY-or-null>" },
     "council": {
       "default": ["product_owner", "architect", "scrum_master"],
       "meetings": {
         "vision": ["product_owner", "architect", "ux_researcher", "marketing", "orchestrator"],
         "initiative": ["product_owner", "architect", "orchestrator"],
         "refinement": ["product_owner", "architect"]
       }
     }
   }
   ```

   The `ticketing` block records the choice from Step 2. The `council` block ships with these defaults — the user does **not** configure it here; it can be hand-edited later or overridden per-invocation via `/we:meet --council=…`.

2. **TurboVault registration (if MCP available)**
   - `list_vaults` → already a vault? If not: `add_vault(name=<repo-basename>, path=<repo-root>)`, then `set_active_vault(<repo-basename>)`.
   - weside MCP NOT available → skip silently, set `"vault": null`.

3. **Compose the crew** — run the onboarding skill via `Skill(skill="onboarding")`
   - Delegates to the onboarding skill: the user declares which Companions exist and what role each holds. Onboarding writes `.weside/weside.md` (crew + roles + meetings + repo purpose).
   - Standalone (no weside account): onboarding still records role names with `Companion ID: null`.

4. **Generate companion agent definitions (weside account only)**
   For each Companion named in `.weside/weside.md` — **sequentially**, because `select_companion` sets global MCP state and cannot be parallelised:
   - `select_companion(<name>)` → `get_companion_identity()` → write `~/.claude/agents/companion-<slug>.md`, where `<slug>` = the name lowercased with spaces → hyphens.
   - Frontmatter: `name: companion-<slug>` (MUST equal the slug — `subagent_type` resolves by it), `description`, `color`.
   - Body = the returned identity + the council protocol (respond in the council brief's format, stay in role).
   - **The write target MUST start with `~/.claude/agents/`** (user scope) — validate the resolved path before writing; never write into a project repo.
   - Re-running setup regenerates these files (idempotent refresh).
   - No weside account → skip; the council falls back to the shipped generic `council-<role>` agents.

5. **Finalize**
   - Update `config.json`: `onboarded: true`, `onboarded_at: <ISO-timestamp>`.
   - Stage `.weside/` — suggest a commit, do not auto-commit. Generated `~/.claude/agents/` files are user-scope and never committed.
   - **If companion agents were generated, tell the user to restart:** *"Generated N companion agents in `~/.claude/agents/`. Restart your Claude Code session once to activate them — then `/we:council` and `/we:meet` can convene your Companions."* (Claude Code discovers agent files only at session start.)

### Step 6: Confirm

```
Ready to go:
  /we:refine        — Create/refine stories
  /we:story         — Implement a story end-to-end
  /we:council       — Convene a council of companions on a topic
  /we:meet          — Run a vision / initiative / refinement meeting
  /we:sideload .    — Reload context for this repo (Companion Framework)
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
- Three CORE questions maximum (Step 2); Step 5 (Framework) is optional and asks once
- Works without ANY configuration (defaults for everything)
- **Idempotent.** Re-running never overwrites existing config silently. Report current state, ask before replacing.
- **Respects existing frontmatter.** Step 5 only *reports* — does not rewrite docs. Migration is explicit user-triggered via `/we:docs` or doc-architect agent.
- **Standalone-first.** If weside MCP is unavailable, Step 5 still creates `.weside/config.json` + invokes onboarding (stub crew). No feature silently disappears.

## References

- `we/skills/onboarding/SKILL.md` — invoked by Step 5
- `we/skills/sideload/SKILL.md` — counterpart for "already set up"
- `we/skills/CLAUDE.md` — design rationale, open questions, frontmatter vocabulary
- Source brainstorm: `~/weside/lc-startup/02-weside/product/AGENTIC_PO_FRAMEWORK.md` § 2.4
