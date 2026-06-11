---
name: sideload
description: >
  Load a neighbor repo's essential context (CLAUDE.md + ALL rules + crew)
  into the current session without leaving it. A stopgap — prefer a native
  session in the target repo. Triggers: sideload, load context for,
  cross-repo, work on other repo, come up to speed.
---


# /we:sideload

> **Sideload is a stopgap — avoid it when you can.** A native Claude Code session
> started *inside* the target repo gets that repo's path-filtered rules lazily from
> the harness, exactly when it touches a matching file. A sideloaded main agent is
> rooted in the *wrong* repo, so the harness never injects those rules for it. There is
> no reliable subset to load — either everything, or gaps the moment you edit. So
> sideload loads **every** rule eagerly (expensive, fills the window). Use it only for
> genuine cross-repo situations where switching to a native session in the target repo
> is not practical. When in doubt, open the target repo natively instead.

**Purpose:** When you must work on a neighbor repo without leaving the current session,
load enough context — CLAUDE.md, every rule, the crew — that the main agent can actually
work there, not just orient itself.

## Invocation

```
/we:sideload <repo-name-or-path>
/we:sideload .                     # current repo
/we:sideload backend-repo          # sibling repo by basename
/we:sideload ../another-repo        # explicit path
```

## Workflow

1. **Resolve target repo**
   - Input is a repo basename (sibling-directory search) or an absolute path
   - If basename: search the sibling directories of the current repo's parent
   - Verify `.weside/config.json` exists → else use the [Fallback](#fallback-legacy-repo-without-setup-yet)

2. **Activate vault** (best-effort — skip silently if MCP/vault unavailable)
   - Read `.weside/config.json` → `vault` name
   - `mcp__turbovault__set_active_vault(<vault>)` (if MCP available)
   - If vault not registered yet → offer to `add_vault` now (edge case)

3. **Layer 1 — SHAPE (cheap overview)**
   - `mcp__turbovault__explain_vault()` → structure/stats summary (if MCP available)
   - Keep this short — just gives shape of the repo

4. **Layer 2 — ESSENTIALS (the actual must-knows)**

   - `<repo>/CLAUDE.md` — unconditional, the entry point. Load first.

   - **ALL rules, eager.** If `<repo>/.claude/rules/` exists, glob `**/*.md` under it and
     read **every** file — no frontmatter filter, no role filter, no path filter.
     A native agent would receive the always-loaded rules immediately and the
     path-filtered ones lazily as it edits matching files; a sideloaded main agent gets
     neither for free, so it must load the whole set up front. This is the expensive part
     and the reason sideload is a stopgap (see the banner above).

5. **Layer 3 — WESIDE (companion-facing knowledge)**
   - Read `<repo>/.weside/weside.md` — everything the companion needs to know to work here:
     repo purpose, crew, meetings, cross-repo relations
   - Print a short summary derived from its `## Crew` section, e.g. "Crew on this repo:
     <PO name> (PO), <Architect name> (Architect), <SM name> (SM)"

6. **Report**
   ```
   Contextualized for <repo-name>.  (stopgap — prefer a native session here)
     Shape: <N docs, M rules>
     Rules loaded: <K> (all, eager)
     Crew: <names and roles>
   Ask for specific docs via `/we:search` or just ask naturally.
   ```

## Fallback (legacy repo without setup yet)

If `.weside/config.json` doesn't exist:
- Read `<repo>/CLAUDE.md` (if exists)
- Glob `<repo>/.claude/rules/**/*.md` and read **all** of them (same eager load as the
  happy path — no directory-name assumptions, just every rule under `.claude/rules/`)
- Skip vault steps
- Print: "No .weside/ found — ran in legacy mode. Run `/we:setup` in that repo for vault + crew context."

This makes `/we:sideload` useful even before any repo is fully onboarded.

## Rules

- **Load ALL rules — on purpose.** Sideload is not a frugal mode; it is a stopgap for a
  main agent rooted in the wrong repo. A native session in the target repo is always the
  better choice — prefer it whenever switching is practical.
- **CLAUDE.md is always loaded.** Non-negotiable, first.
- **No directory-name assumptions.** Find rules via the `.claude/rules/**/*.md` glob, never
  by hardcoded subfolders — the plugin is generic and can't anticipate a repo's layout.
- **Degrade gracefully.** No MCP / no vault → still load CLAUDE.md + all rules (legacy mode).
- **Read-only operation.** `/we:sideload` never modifies the target repo. Migration/curation
  belongs in `/we:setup` or `/we:docs`.
- **Session state.** Track which repos are currently "entered" so we don't reload redundantly
  within one session. (Implementation detail — maybe session-scoped file under `/tmp`.)

## References

- `we/skills/setup/SKILL.md` — sets up a repo for `/we:sideload` to work
- `we/skills/onboarding/SKILL.md` — produces the `weside.md` this skill reads
- `we/skills/CLAUDE.md` — design rationale
