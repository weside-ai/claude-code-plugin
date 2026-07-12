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
| `/we:meet` | Structured meetings at four Plan altitudes (vision / saga / epic / story) built on the council |
| `/we:vision`, `/we:saga`, `/we:epic`, `/we:story` | Solo formulation skills at each Plan altitude — companion-aware artifact authoring |

**No-account invariant:** every framework skill works **without** a weside account. Companion features are strictly *additive* — without an account the council falls back to shipped generic role-agents, `/we:sideload` runs in legacy mode, and meetings run solo. An account upgrades the experience; it is never a prerequisite.

**Council member source — `loadCouncilFromWeside`:** governs whether convened members are weside-backed Companions or generic role-lenses. Semantics + the branch that acts on it: `we/skills/council/SKILL.md` Step 3 (the single owner). A council is a roster of role-lenses, each generic OR weside-backed; mixed is normal.

## Activity skills vs. meeting skills

Two categories — both needed, kept separate:

| Category | Who | When | Examples |
|---|---|---|---|
| **Activity / Solo** | one companion works alone in a role | scope is clear, routine work | `/we:vision`, `/we:saga`, `/we:epic`, `/we:story`, `/we:build`, `/we:pr`, `/we:ac-review` |
| **Meeting** | several companions + stakeholder coordinate | a decision or alignment is needed | `/we:meet vision`, `/we:meet saga`, `/we:meet epic`, `/we:meet story` |

A meeting produces decomposition + a synthesis; an activity produces the artifact. `/we:meet story` hands off to `/we:story` (Solo) once the crew has agreed the scope; the other meetings (vision/saga/epic) hand off to the matching Solo skill (`/we:vision`/`/we:saga`/`/we:epic`) for the artifact write. Meetings live in **one** argument-dispatched skill, `we/skills/meet/` — the plugin loader does not support nested skill directories.

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

The council ships generic agents for nine roles: `architect`, `product_owner`, `scrum_master`, `ux_researcher`, `orchestrator`, `marketing`, `security`, `sales`, `legal`. A weside crew may define further custom roles — those require a companion assigned to the role, since no generic agent ships for them. Custom roles without an assigned companion are skipped (and named in the council output) per `we/skills/council/SKILL.md` Step 3's "Unknown role" rule.

## `.weside/` — repo-scoped config

Produced by `/we:setup` + `/we:onboarding`, committed into the repo so crew and config are versioned per-repo:

| File | Audience | Holds |
|---|---|---|
| `config.json` | tooling (machine-readable) | `vault`, `framework_version`, `onboarded`, `ticketing`, `stack`, `council` (per-meeting rosters) |
| `weside.md` | companion (human-readable) | repo purpose, crew (names + roles), meetings, cross-repo relations |
| `council.json` | tooling (machine-readable, **gitignored**) | per-member crew membership: `role`, `color`, `companion_id`, display `name` per slug. Companion-Framework bridge file, written by `/we:onboarding` (or `scripts/bootstrap-weside-repo.py` for bulk rollout). Two schemas accepted (`thin` — preferred, no identity; `fat` — legacy, with `identity_prompt`). See "The bridge file" below. |

Rule of thumb: if a human or companion reads it to *understand the repo* → `weside.md`; if a skill reads it to *decide what to do* → `config.json`. `council.json` is the exception that is **gitignored** even in its thin form — Companion IDs and crew structure are private to the user's weside account and shouldn't propagate into project repos that may be public.

## Meetings & council — the cycle motif

A meeting (`/we:meet vision|saga|epic|story`) wraps a council in a structured workflow. A council convenes role-lens agents into a **live Claude Code Agent Team** — they deliberate in a shared channel, addressing each other directly via `SendMessage`. The **lead session** (the one that ran `/we:council`) is the orchestrator: it observes the chatter, closes the deliberation when it is ripe, runs the final-position round, and writes the synthesis (*agreement, tension, and recommendation*). Full mechanics in `we/skills/council/SKILL.md`.

Live councils require Claude Code's experimental Agent Teams feature (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in `~/.claude/settings.json`'s `env` block). `/we:setup` Step 5.0 sets this on request. The pre-v2.31.0 fan-out path — parallel sub-agents writing isolated memos — was removed; there is no fallback. If the flag is missing, the skill aborts with a remediation hint.

The council is a **cycle**, not a one-shot read: load → deliberate → **write-back**. A Companion that sat in a council *comes out changed* — what the council decided is part of what they know next time. Today, the write-back path is manual (the user copies the synthesis into a memory or doc); the Phase-6 form of `get_council` (team-scoped memory + workspace_id) will close the loop automatically. Design rationale: see the associated team repo's plan for the Phase-6 backend work.

## Identity loading — two paths

Identity comes from MCP `get_council` (preferred) or the bridge fat-schema fallback, with
`companion-<slug>` files and the generic `council-<role>` shells below that. The executable
precedence + call mechanics are owned by `we/skills/council/SKILL.md` Step 3 — this file
deliberately does not restate them.

## The bridge file `.weside/council.json`

The bridge file declares **which Companions are in this repo's crew, in which role, with which color**. It is the role-membership record on the file system, paired with weside's identity store via MCP.

**Thin schema (preferred):** the JSON shape is owned by `/we:onboarding` Step 8 (the writer —
`we/skills/onboarding/SKILL.md`); `scripts/bootstrap-weside-repo.py` emits the same shape for
non-interactive multi-repo rollout.

**Fat schema (legacy, accepted for back-compat):** same shape plus an `identity_prompt` and `identity_updated_at` per member. Used in pre-v2.25.0 repos that hand-authored identity bodies into the file. New bridges are written thin; an existing fat bridge keeps working unchanged (and `scripts/bootstrap-weside-repo.py` migrates it fat → thin on its next run).

**Both schemas live under the same path** (`<repo>/.weside/council.json`). The council skill detects which one is present by checking for `identity_prompt` keys.

**How `/we:council` consumes it:**
- Thin schema → role/color/membership for the call; identity comes from `get_council` MCP.
- Fat schema → role/color/membership + identity (the pre-MCP path, still works).
- Either way the bridge stays **gitignored** — Companion IDs and crew structure are private; both bridge writers (`/we:onboarding` and `scripts/bootstrap-weside-repo.py`) append `.weside/council.json` to `.gitignore`.

**Why workspace_id is null in v1:** the bridge's selector role (which team in weside is this repo serving?) is gated on Phase 6 (team/workspace model). Until then, every bridge is implicitly user-scoped. Phase-6 backend work will cover what changes when Phase 6 lands.

**Refresh:** thin bridge changes only when the crew composition changes (new member, role swap, color change). Identity changes are picked up automatically via MCP on the next `/we:council`; no file edit needed.
