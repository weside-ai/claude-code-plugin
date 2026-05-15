---
need_to_know: true
for_role: [scrum_master, product_owner, architect]
need_to_know_reason: "Companion Framework design vocabulary and .weside/ structure — essential context when working on the framework skills"
type: foundation
status: current
---

# Skills Workspace — Companion Framework Design Notes

Loaded hierarchically when working inside `we/skills/`. It captures the **Companion Framework** design vocabulary and conventions the framework skills share. This is design rationale — the skills themselves remain the source of truth for what they do.

## The Companion Framework

The framework lets a user's weside Companions work as a real crew inside Claude Code:

| Skill | Purpose |
|---|---|
| `/we:setup` | Project onboarding + Companion Framework init (`.weside/`, vault, crew, companion agents) |
| `/we:onboarding` | Interactive crew composition → writes `.weside/weside.md` |
| `/we:sideload` | Load a repo's essential context (3 layers: shape → essentials → crew) |
| `/we:council` | Convene a council of companion-agents to deliberate on a topic |
| `/we:meet` | Structured meetings (vision / initiative / refinement) built on the council |

**No-account invariant:** every framework skill works **without** a weside account. Companion features are strictly *additive* — without an account the council falls back to shipped generic role-agents, `/we:sideload` runs in legacy mode, and meetings run solo. An account upgrades the experience; it is never a prerequisite.

## Activity skills vs. meeting skills

Two categories — both needed, kept separate:

| Category | Who | When | Examples |
|---|---|---|---|
| **Activity** | one companion works alone in a role | scope is clear, routine work | `/we:refine`, `/we:story`, `/we:pr`, `/we:review` |
| **Meeting** | several companions + stakeholder coordinate | a decision or alignment is needed | `/we:meet vision`, `/we:meet initiative`, `/we:meet refinement` |

A meeting produces consensus; an activity produces the artifact. `/we:meet refinement` hands off to `/we:refine` once the crew has agreed the scope. Meetings live in **one** argument-dispatched skill, `we/skills/meet/` — the plugin loader does not support nested skill directories.

## Frontmatter vocabulary

Applies to docs and rules that `/we:sideload` consumes:

```yaml
---
need_to_know: true                     # /we:sideload loads this on entry (default: false)
for_role: [architect, product_owner]   # optional; omit → applies to all roles
need_to_know_reason: "why this is essential when entering"
---
```

**Criterion for `need_to_know: true`:** *could someone work here without having read this file?* No → `need_to_know: true`. Yes → omit. This is stricter than the always-loaded rule convention — not every always-loaded rule is entry-essential.

### Role slugs

The council ships generic agents for six roles: `architect`, `product_owner`, `scrum_master`, `ux_researcher`, `orchestrator`, `marketing`. A weside crew may define further roles (e.g. `sales`, `legal`) — those require a companion assigned to the role, since no generic agent ships for them.

## `.weside/` — repo-scoped config

Produced by `/we:setup` + `/we:onboarding`, committed into the repo so crew and config are versioned per-repo:

| File | Audience | Holds |
|---|---|---|
| `config.json` | tooling (machine-readable) | `vault`, `framework_version`, `onboarded`, `ticketing`, `stack`, `council` (per-meeting rosters) |
| `weside.md` | companion (human-readable) | repo purpose, crew (names + roles), meetings, cross-repo relations |

Rule of thumb: if a human or companion reads it to *understand the repo* → `weside.md`; if a skill reads it to *decide what to do* → `config.json`. No secrets belong in `.weside/` — companion identity material lives in the weside account, referenced only by name and role.
