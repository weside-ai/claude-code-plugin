---
name: sideload
description: >
  Loads a neighbour repo's CLAUDE.md, all rules and crew into this session — a stopgap; a native
  session there is better. Triggers: "/we:sideload", "load context for", "cross-repo".
---

# /we:sideload

> **Prefer a native session in the target repo.** A session started *inside* a repo gets that
> repo's path-filtered rules from the harness, lazily, exactly when it touches a matching file. A
> sideloaded agent is rooted in the **wrong** repo, so the harness never injects them — and there is
> no reliable subset to pick, because you find out which rule you needed at the moment you edit.
> So sideload loads **every** rule eagerly and fills the window. Use it only when switching is
> genuinely impractical.

**Purpose:** when you must work on a neighbour repo without leaving this session, load enough that
the agent can actually work there — not just orient itself.

```
/we:sideload <repo-name-or-path>     # basename → sibling-directory search, or an explicit path
/we:sideload .                       # current repo
```

## Workflow

1. **Resolve the target** — a basename resolves against the sibling directories of the current
   repo's parent; a path is used as-is.

2. **Activate its vault** (best-effort): read `.weside/config.json` → `vault`, then
   `set_active_vault`. Not registered → offer `add_vault`. No MCP → skip silently.

3. **Layer 1 — shape:** `explain_vault()` for a structure/stats overview. Keep it short; this only
   gives the outline.

4. **Layer 2 — essentials:** `<repo>/CLAUDE.md` first, unconditionally. Then **every** file under
   `<repo>/.claude/rules/**/*.md` — no frontmatter filter, no role filter, no path filter. This is
   the expensive part and the reason for the banner above. Find them by glob, never by assuming a
   subfolder layout.

5. **Layer 3 — crew:** `<repo>/.weside/weside.md` — repo purpose, crew, meetings, cross-repo
   relations. Print a one-line crew summary from its `## Crew` section.

6. **Report** what was loaded (docs, rules count, crew) and repeat that a native session there is
   the better move. Then work — further docs get read on demand.

**No `.weside/` in the target** → legacy mode: CLAUDE.md + every rule, skip the vault steps, and say
so once. That makes sideload useful before a repo is onboarded.

## Rules

- **Loading all rules is the design, not an oversight** — a frugal sideload is a broken sideload.
- **Read-only in the target repo.** Migration and curation belong to `/we:setup` or the `we:doc-architect` agent.
- **Degrade quietly.** No MCP, no vault, no `.weside/` — CLAUDE.md plus the rules still load.
- Track which repos are already loaded this session; don't reload one twice.

## References

- `we/skills/setup/SKILL.md` — what makes a repo sideload-ready
- `we/skills/onboarding/SKILL.md` — writes the `weside.md` this skill reads
