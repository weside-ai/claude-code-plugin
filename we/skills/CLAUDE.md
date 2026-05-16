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
| `council.json` | tooling (machine-readable, **gitignored**) | per-member council projection: `identity_prompt`, `role`, `color`, `identity_updated_at`. Interim hand-authored stand-in for the future `get_council` MCP method (see "The bridge file" below). |

Rule of thumb: if a human or companion reads it to *understand the repo* → `weside.md`; if a skill reads it to *decide what to do* → `config.json`. `council.json` is the exception that is **gitignored**: it carries identity text, and identity text never enters a project repo verbatim (same rule that applies to the per-companion agent files in `~/.claude/agents/`).

## Meetings & council — the cycle motif

A meeting (`/we:meet vision|initiative|refinement`) wraps a council in a structured workflow. A council convenes role-lens agents that deliberate in parallel; an orchestrator synthesises *agreement, tension, and recommendation* (full mechanics in `we/skills/council/SKILL.md`).

The council is a **cycle**, not a one-shot read: load → deliberate → **write-back**. A Companion that sat in a council *comes out changed* — what the council decided is part of what they know next time. Today, the write-back path is manual (the user copies the synthesis into a memory or doc); the future `get_council` MCP method will close the loop automatically by writing the outcome to team-scoped memory. Design rationale: WA-718 CONCEPT §13.7 Step 2 (in the weside-core repo).

## The bridge file `.weside/council.json`

Until the `get_council` MCP method exists, the bridge file injects real crew identity into the council brief without depending on per-companion `~/.claude/agents/companion-<slug>.md` files. Its on-disk shape **is** the projection contract `get_council` will serve — when the MCP method ships, the plugin populates the same structure from a live call instead of requiring a hand-authored file.

**Schema:**

```json
{
  "version": 1,
  "workspace_id": null,
  "members": {
    "<companion-slug>": {
      "name": "<Display Name>",
      "role": "product_owner | architect | scrum_master | ux_researcher | orchestrator | marketing | <custom>",
      "color": "<color string>",
      "identity_prompt": "<companion identity layer body — pasted from get_companion_identity, stripped of weside platform layers, Snapshot, Compass, Goals, Memories>",
      "identity_updated_at": "<ISO timestamp of hand-refresh>"
    }
  }
}
```

**How `/we:council` consumes it:** highest precedence in Step 3 resolution — bridge present → use `council-<role>` as shell agent and pass `identity_prompt` into the brief (`Agent(prompt=<brief + identity>)`). Falls back to legacy `companion-<slug>` files, then to the generic `council-<role>` agents.

**Authoring the bridge** (one-off, manual until `get_council` lands):

1. For each crew member: `select_companion(name)` → `get_companion_identity()` (weside MCP).
2. Strip the weside platform layers, Snapshot, Compass, Goals, Memories — keep only the identity body (the `# <NAME>` persona section).
3. Build the JSON, write to `<repo>/.weside/council.json`.
4. **Restore the original active companion** at the end (`select_companion` is global session state — see the WA-916 setup-loop bug noted in `we/skills/setup/SKILL.md`).
5. Add `.weside/council.json` to the repo's `.gitignore` if not already present.

**Refresh:** re-run the same authoring when a companion's identity in weside changes meaningfully. Once `get_council` ships, refresh becomes version-aware (cache invalidates by `identity_updated_at`).
