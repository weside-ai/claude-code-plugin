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

### Step 1b: Check Plugin Dependencies

Check if recommended companion plugins are installed. Read `~/.claude/plugins/installed_plugins.json` or check if the skill appears in available skills.

| Plugin | Provides | Used By |
|--------|----------|---------|
| `code-simplifier@claude-plugins-official` | `/simplify` skill | Step 4: Simplify in `/we:story` |
| `security-guidance@claude-plugins-official` | Security hooks during development | `/we:story` Step 2 security checks |

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

### Step 4: Confirm core config

```
Project configured!

Stack: Python + TypeScript (monorepo)
Ticketing: Jira (project: PROJ)
Vision: .weside/vision.md
```

### Step 5: Companion Framework Setup (optional — ask first!)

> **🚧 Status: evolving.** See `we/skills/CLAUDE.md` for the full design + open questions.

Ask: *"Do you want to set up the Companion Framework for this repo now? (Crew + TurboVault context-loading + frontmatter). You can also run `/we:onboarding` later."*

If **no** → skip to Step 6.

If **yes**:

1. **Ensure `.weside/config.json`** — create or extend. Minimum schema:
   ```json
   {
     "vault": "<repo-basename>",
     "onboarded": false,
     "created_at": "<ISO-timestamp>",
     "framework_version": 1
   }
   ```

2. **TurboVault registration (if MCP available)**
   - `list_vaults` → is this repo's path already a vault?
   - If not: `add_vault(name=<repo-basename>, path=<repo-root>)`
   - `set_active_vault(<repo-basename>)`
   - If weside MCP is NOT available → skip silently, note in config `"vault": null`

3. **Frontmatter audit (report only, no migration yet)**
   - `inspect_frontmatter` → which keys are present across docs?
   - Report: coverage %, how many docs have `need_to_know: true`, how many have `for_role`
   - Suggestion: "Run doc-architect agent to migrate frontmatter across docs — see `/we:docs`"

4. **Invoke `/we:onboarding`**
   - Delegates to the onboarding skill (crew composition + repo-companion knowledge)
   - Onboarding writes `.weside/weside.md` (companion-facing knowledge: crew, meetings, repo purpose)

5. **Finalize**
   - Update `config.json`: `onboarded: true, onboarded_at: <ts>`
   - Stage `.weside/` — suggest commit but do not auto-commit
   - Print: *"Framework ready. Run `/we:sideload <repo>` from any session to load context."*

### Step 6: Confirm

```
Ready to go:
  /we:refine     — Create/refine stories
  /we:story      — Implement a story end-to-end
  /we:review     — Code review
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

## Open Questions (see we/skills/CLAUDE.md)

- Auto-fire Step 5 on fresh setup vs. always ask?
- Frontmatter migration: who kurates `need_to_know: true` — doc-architect agent or user?
- Crew-Portabilität: "copy from other repo" flow?
- Rollback wenn Setup mittendrin abbricht?

## References

- `we/skills/onboarding/SKILL.md` — invoked by Step 5
- `we/skills/sideload/SKILL.md` — counterpart for "already set up"
- `we/skills/CLAUDE.md` — design rationale, open questions, frontmatter vocabulary
- Source brainstorm: `~/weside/lc-startup/02-weside/product/AGENTIC_PRODUCT_OWNERSHIP.md` § 2.4
