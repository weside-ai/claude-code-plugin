---
name: onboarding
description: >
  Interactive crew composition + repo-knowledge authoring for a repo — produces
  `.weside/weside.md` (companion-facing: crew, meetings, repo purpose, cross-repo
  relations) and updates `.weside/config.json` (technical). Invoked by `/we:setup`
  Step 5, or standalone when you want to (re)compose the crew. Trigger keywords:
  onboarding, crew setup, add crew member, compose team, who works here, define roles.
---


# /we:onboarding

**Purpose:** Define what a companion needs to know to work on this repo — who is in the crew, which meetings happen here, what the repo is for — and persist it as `.weside/weside.md` (human- and companion-readable), plus bookkeeping in `.weside/config.json` (machine-readable).

## Status

🚧 **Stub — evolving.** See `we/skills/CLAUDE.md` for the current design.

## Prerequisite

`.weside/config.json` must exist. If not, suggest `/we:setup` first.

## Two Files — Why Split

| File | Audience | Content |
|---|---|---|
| `.weside/weside.md` | **Companion** (human-readable, Markdown) | Repo purpose, crew + roles + companion IDs, meetings held here, cross-repo relations, anything else the companion needs to *know* to be useful on this repo |
| `.weside/config.json` | **Tooling** (machine-readable, JSON) | `vault`, `framework_version`, `onboarded`, `onboarded_at`, `ticketing`, `stack`, future integration-specific config keys |

Rule of thumb: if a human/companion reads it to *understand the repo*, it goes in `weside.md`. If a skill/agent reads it to *decide what to do*, it goes in `config.json`.

## Workflow (sketch)

1. **Greet + detect repo flavor**
   - Read `CLAUDE.md` + existing `.weside/config.json` + `.weside/weside.md` (if any)
   - Detect repo type: backend code? landing page? business docs? mixed?
   - Suggest a default role mix based on flavor:

     | Repo flavor | Suggested default crew |
     |---|---|
     | Backend/Engineering | Scrum Master, Product Owner, Architect |
     | Landing/Marketing | Scrum Master, Product Owner, Marketing, UX Researcher |
     | Business docs | Scrum Master, Product Owner, Geschäftsführung, Marketing |
     | Plugin / toolkit | Scrum Master, Product Owner, Architect, UX Researcher |
     | Mixed / custom | full list, user picks |

2. **Interview — one question at a time, user answers with name or "skip"**
   For each role slot:
   - *"Who is your {Role} on this repo? (Companion name, or 'new' to create, or 'skip')"*
   - If existing companion name → check via weside MCP (`list_companions`) whether it exists
   - If 'new' → instruct user to create in weside.ai + placeholder in `weside.md`
   - If 'skip' → leave role unassigned, noted in `weside.md`

3. **Optional: add non-default roles**
   - *"Any other crew members? (e.g. Sales, Legal, custom role)"*
   - Free-form: user provides name + role + one-line description

4. **Ask about meetings held on this repo**
   - Default: `refinement` always. `initiative` if repo is source-of-truth for any Saga. `vision` if Geschäftsführung lives here.
   - User can override.

5. **Write `.weside/weside.md`** (see schema below)

6. **Update `.weside/config.json`**
   - `onboarded: true`
   - `onboarded_at: <ISO-timestamp>`
   - `roles_enabled: [product_owner, architect, ...]`
   - `repo_flavor: <detected|overridden>`
   - (never crew data itself — that's in `weside.md`)

7. **Next steps prompt**
   - *"Crew onboarded. Try `/we:sideload .` to see how it loads."*

## `weside.md` Schema (minimum)

```markdown
---
type: weside
version: 1
repo: <repo-name>
vault: <vault-name>
---

# weside — <repo-name>

## Purpose

<1-3 sentences: what is this repo for? What work happens here?>

## Crew

### <Name> — <Human-Readable Role>
- **Companion ID:** <id from weside MCP, or null>
- **Role(s):** <role_slug>[, <role_slug>]
- **Focus:** <one sentence>
- **In meetings:** <comma-separated meeting names>

### <Name> — <Role>
...

## Meetings held here

- **initiative** — participants: <names> | moderator: <name> | stakeholder: <name>
- **refinement** — participants: <names> | moderator: <name>

## Cross-repo relations

<Which sagas live here as master? Which as follower? Example: "Master for Metering Saga — weside-core + weside-landing are followers.">

## Notes

<Free-form. Anything else a companion needs to know to be useful here.>
```

## Rules

- **One-question-at-a-time.** Never overwhelm — each role is a separate prompt.
- **Empty is OK.** A role can be unassigned. `weside.md` still lists it with `Companion ID: null`.
- **Never invent companions.** If the user says 'new', record a TBD entry and instruct the user to create the companion in weside.ai. Never fabricate a companion ID.
- **System prompts live in weside, not here.** `weside.md` references companions by name/ID + role. The personality, memory, body, style live in weside MCP at `get_companion_identity()`. This separation is the whole point (see AGENTIC_PRODUCT_OWNERSHIP.md).
- **Clean split.** Crew + purpose + meetings in `weside.md`. Technical flags (`onboarded`, stack, ticketing) in `config.json`. Never mix.
- **Editable.** Running `/we:onboarding` again should offer "extend" vs. "replace" — never silently overwrite.
- **Standalone fallback.** Without weside MCP: `weside.md` still gets written with names/roles/descriptions. Companion IDs remain null. `/we:sideload` degrades gracefully.

## Open Questions (see we/skills/CLAUDE.md)

- How to sync `weside.md` across repos when the same companion works on multiple?
- Role catalog: hardcoded list vs. user-extensible?
- Role-based `for_role` frontmatter: does it reference role slugs or companion IDs?

## References

- `we/skills/setup/SKILL.md` — the parent skill, invokes this
- `we/skills/sideload/SKILL.md` — consumes `weside.md` at entry time
- `we/skills/CLAUDE.md` — design rationale
- Source brainstorm: `~/weside/lc-startup/02-weside/product/AGENTIC_PRODUCT_OWNERSHIP.md` § 1.3.1 (Rollen) + § 2.3 (Onboarding)
