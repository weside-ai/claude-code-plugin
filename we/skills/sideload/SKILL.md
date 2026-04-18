---
name: sideload
description: >
  Load a repo's essential context (CLAUDE.md + need-to-know docs/rules + crew) into the
  current session — even for repos you haven't cd'd into. Sideloading means pulling a
  neighbor repo's context in from the side without leaving the current one. Optionally
  filters by your current role. Trigger keywords: sideload, switch repo, load context for,
  work on other repo, cross-repo, need-to-know, load crew, come up to speed, enter repo.
---


# /we:sideload

**Purpose:** When you're about to work on a repo — either switching from another or collaborating across repos — load the minimum essential context without flooding your window with every rule.

## Status

🚧 **Stub — evolving.** See `we/skills/CLAUDE.md` for full design.

## Invocation

```
/we:sideload <repo-name-or-path>
/we:sideload .                     # current repo
/we:sideload weside-core           # sibling repo by basename
/we:sideload ~/weside/lc-startup   # explicit path
/we:sideload <repo> --role=architect   # filter need-to-know docs by role
/we:sideload <repo> --full              # ignore role filter, load everything
```

## Workflow

1. **Resolve target repo**
   - Input is repo basename (sibling search under `~/weside/`) or absolute path
   - If basename: search `~/weside/<name>` and `~/<workspace>/<name>`
   - Verify `.weside/config.json` exists → else print: "Run `/we:setup` in that repo first"

2. **Activate vault**
   - Read `.weside/config.json` → `vault` name
   - `mcp__turbovault__set_active_vault(<vault>)` (if MCP available)
   - If vault not registered yet → offer to `add_vault` now (edge case)

3. **Layer 1 — SHAPE (cheap overview)**
   - `mcp__turbovault__explain_vault()` → structure/stats summary
   - Keep this short — just gives shape of the repo

4. **Layer 2 — ESSENTIALS (the actual must-knows)**
   Always load:
   - `<repo>/CLAUDE.md` — unconditional, the entry point

   Then search for flagged docs:
   - `mcp__turbovault__search_by_frontmatter(key="need_to_know", value="true")`
   - If `--role=<slug>` passed: filter results where `for_role` includes that slug OR is missing (missing = applies to all roles)
   - If `--full` passed: no role filter, load all `need_to_know: true`
   - Read each matching file → inject into context

5. **Layer 3 — WESIDE (companion-facing knowledge)**
   - Read `<repo>/.weside/weside.md` — everything the companion needs to know to work here: repo purpose, crew, meetings, cross-repo relations
   - Print a short summary derived from its `## Crew` section: "Crew on this repo: Pia (PO), Vyra (Architect), Samu (SM)"

6. **Report**
   ```
   Contextualized for <repo-name>.
     Shape: <N docs, M rules>
     Essentials loaded: <K files>
     Role filter: <architect | none>
     Crew: <names and roles>
   Ask for specific docs via `/we:search` or just ask naturally.
   ```

## Frontmatter it consumes

```yaml
---
need_to_know: true              # enter will load this
for_role: [architect, po]       # optional; omit = all roles
need_to_know_reason: "..."      # optional; human-readable rationale
---
```

## Fallback (legacy repo without setup yet)

If `.weside/config.json` doesn't exist but the user insists:
- Read `<repo>/CLAUDE.md` (if exists)
- Read `<repo>/.claude/rules/core/*.md` (always-loaded convention)
- Read `<repo>/.claude/rules/workflows/*.md` (always-loaded convention)
- Skip vault steps
- Print: "No .weside/ found — ran in legacy mode. Run `/we:setup` in that repo for full context loading."

This makes `/we:sideload` useful even before any repo is fully onboarded.

## Rules

- **Don't load everything.** Role filter + need_to_know flag are the point. "Full" mode is opt-in, not default.
- **CLAUDE.md is always loaded.** Non-negotiable, independent of frontmatter.
- **Degrade gracefully.** No MCP / no vault / no frontmatter → still useful (legacy mode).
- **Read-only operation.** `/we:sideload` never modifies the target repo. Migration/curation belongs in `/we:setup` or `/we:docs`.
- **Session state.** Track which repos are currently "entered" so we don't reload redundantly within one session. (Implementation detail — maybe session-scoped file under `/tmp`.)

## Open Questions (see we/skills/CLAUDE.md)

- Binary `need_to_know` vs. levels (`L1`/`L2`/`L3`)?
- `for_role` taxonomy — how strict? Free-form vs. enumerated?
- Auto-fire via PreToolUse hook when accessing files in a different repo?
- Should `/we:sideload` print diff-mode ("since last entered, these docs changed")?

## References

- `we/skills/setup/SKILL.md` — sets up a repo for `/we:sideload` to work
- `we/skills/onboarding/SKILL.md` — produces the `weside.md` this skill reads
- `we/skills/CLAUDE.md` — design rationale + frontmatter vocabulary
- Source brainstorm: `~/weside/lc-startup/02-weside/product/AGENTIC_PRODUCT_OWNERSHIP.md` § 2.4
