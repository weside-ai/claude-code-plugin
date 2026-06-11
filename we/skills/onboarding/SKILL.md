---
name: onboarding
description: >
  Interactive crew composition — builds the repo's council from scratch
  (assign existing Companions, create new ones, or generic role-lenses) and
  writes .weside/weside.md + council.json + config.json. Invoked by /we:setup
  Step 5 or standalone. Triggers: onboarding, crew setup, build a council,
  compose team, who works here.
---


# /we:onboarding

**Purpose:** Build the repo's **council** — the roster of role-lenses `/we:council` and `/we:meet` convene — and persist what a companion needs to know to work here. Produces `.weside/weside.md` (human- and companion-readable), `.weside/council.json` (the council bridge), and bookkeeping in `.weside/config.json` (machine-readable).

This skill works **from scratch**: with no Companions, no `.weside/`, and no weside account, it still produces a working council (generic role-lenses). With a weside account it guides the user to back individual lenses with real Companions — for the value, the memory, the voice.

## Prerequisite

`.weside/config.json` must exist. If not, suggest `/we:setup` first (it creates it, then delegates here).

## The mental model — lenses, real or generic

A **council** convenes one agent per role to think a topic through from several angles. Each role is a **lens**. Two ways a lens can be filled:

- **Generic lens (Retorte)** — the shipped `council-<role>` agent. Free, works with no account, no limit. A solid role-angle, but no identity or memory.
- **weside-backed lens** — one of the user's weside Companions, carrying real identity + memory + voice. Costs a Companion slot (`plan.max_companions`).

A good council is **mixed**: the roles the user cares most about backed by real Companions, the rest generic. This skill builds exactly that, degrading gracefully when the plan's Companion budget runs out.

## Three files — why split

| File | Audience | Content |
|---|---|---|
| `.weside/weside.md` | **Companion** (human-readable, Markdown) | Repo purpose, crew + roles + companion IDs, meetings held here, cross-repo relations, anything else the companion needs to *know* to be useful on this repo |
| `.weside/council.json` | **Tooling** (machine-readable, **gitignored**) | The council bridge: per-role membership — `role`, `color`, `companion_id` (weside-backed) or `lens` (generic), display `name`. `/we:council` reads this to resolve members. |
| `.weside/config.json` | **Tooling** (machine-readable) | `vault`, `framework_version`, `onboarded`, `onboarded_at`, `ticketing`, `stack`, `council` rosters, future integration keys |

Rule of thumb: human/companion reads it to *understand the repo* → `weside.md`; a skill reads it to *resolve members* → `council.json`; a skill reads it to *decide what to do* → `config.json`.

## Workflow

### 1. Greet + detect repo flavor + read state

- Read `CLAUDE.md` + existing `.weside/config.json` + `.weside/weside.md` + `.weside/council.json` (if any).
- Detect repo type: backend code? landing page? business docs? plugin/toolkit? mixed?
- Suggest a default council roster based on flavor:

  | Repo flavor | Suggested council roster |
  |---|---|
  | Backend/Engineering | Scrum Master, Product Owner, Architect, Security |
  | Landing/Marketing | Scrum Master, Product Owner, Marketing, UX Researcher |
  | Business docs | Scrum Master, Product Owner, Marketing, Legal |
  | Plugin / toolkit | Scrum Master, Product Owner, Architect, UX Researcher |
  | Mixed / custom | full list, user picks |

- **Re-run check:** if `council.json` already has members, offer **extend** vs **replace** — never silently overwrite.

### 2. Frame the council (the new opener)

Briefly (2-3 sentences) tell the user what they're building: *"I'll build this repo's council — the lenses your `/we:council` and `/we:meet` convene. Each lens is a role. Lenses run generic for free, or you can back them with your real weside Companions for identity and memory. We'll mix as your plan allows."*

If there is **no weside MCP / no account**: say the council will run on generic role-lenses, fully functional, and note that a weside.ai account later lets them back lenses with real Companions. Then run the same roster loop, choosing generic for every role.

### 3. Load existing Companions once

With weside MCP: call `mcp__plugin_we_weside-mcp__list_companions` **once** before the role loop (static for the session) and cache it. This is the menu for "assign an existing Companion" below.

### 4. Walk the roster — one role at a time, three ways each

For each role in the proposed roster, ask one question and offer three ways to fill the lens:

> *"{Role} lens — how do you want to fill it?
> (a) assign an existing Companion · (b) create a new Companion for it · (c) generic lens (free)"*

- **(a) Assign an existing Companion** *(weside account)* — validate the name against the cached `list_companions`, then **link it** to the role in the bridge: `companion_id` = the Companion's id, `color` from `we/agents/council-<role>.md` frontmatter. The Companion participates with its **own identity**; the role-lens is carried by the council brief at convene time (`/we:council` Step 6 tells each member to reason from its role lens). No identity edit is needed for an assigned Companion to argue from the lens.
  - Confirm: *"{name} is now your {Role} — they'll bring the lens via the council brief."*
  - **Do NOT** read-then-`update_companion` to bake the lens in here: the MCP read paths (`get_council`, `get_companion_identity`) return the **composed** prompt (platform layers + identity), not the raw identity-layer body — writing that back as `system_prompt` would corrupt the identity layer. Baking a lens permanently into an existing Companion's identity is a deliberate curation step done with the full raw body via the **weside CLI** (`weside companions identity`) or the Personality Settings in the app — mention this as an optional upgrade, don't attempt it from here.

- **(b) Create a new Companion** *(weside account)* — ask for a name (**alphanumeric, no spaces** — it's the slug) and a one-line description. Then:
  `mcp__plugin_we_weside-mcp__create_companion(name=<name>, personality=<neutral starter>, system_prompt=<seed identity — see below>)`.
  - On success (`{name, id, created}`): bridge entry with `companion_id` = the returned id. Confirm: *"Created {name} (id {id}) as your {Role}."*
  - On error → **graceful degrade**, see step 5.

- **(c) Generic lens (Retorte)** — no Companion. Bridge entry with `companion_id: null` and a `lens` field = a one-line role-angle hint (the user's words, or the role's default angle). `/we:council` injects this hint into the generic `council-<role>` brief.

- **Skip** is always allowed → role unassigned, noted in `weside.md` with `Companion ID: null` and no bridge entry.

### 5. Graceful degrade on the Companion limit

`create_companion` is plan-gated (`plan.max_companions`: Spark 1, Bond 3, Companion 5, Soulmate/Mascot unlimited). When it returns `{error}` containing `COMPANION_LIMIT_REACHED` (or "limit reached"):

- Switch **this role and every remaining create-intent** to a **generic lens** (option c) automatically.
- Say it once, plainly, with the CTA — do not abort, never leave the user stuck:
  > *"Your plan allows N Companions (M/N used), so I'll fill the rest of the council with generic lenses — fully functional. Want more real Companions in your council? Upgrade at weside.ai, then re-run `/we:onboarding` to back the remaining lenses."*
- The result is a **mixed council**: the first roles backed by real Companions, the rest generic. That's the intended shape, not a failure.

### 6. Optional: add non-default roles

*"Any other lenses? (e.g. Sales, Legal, a custom role)"* — free-form: name + role + how to fill it (same three ways). Custom roles (no shipped `council-<role>` agent) **must** be weside-backed, else `/we:council` skips them.

### 7. Meetings held on this repo

Default: `refinement` always. `initiative` if the repo is source-of-truth for a Saga. `vision` if leadership lives here. User can override.

### 8. Write `.weside/council.json` (the bridge) — always, fully

Initialize the **thin** envelope and write a `members` entry for **every filled role** (assigned, created, and generic). This is the file `/we:council` resolves members from — it must be complete, not just the `create` cases.

```json
{
  "version": 2,
  "schema": "thin",
  "workspace_id": null,
  "members": {
    "<slug>": {
      "name": "<Display Name>",
      "role": "<role slug>",
      "color": "<color from council-<role>.md frontmatter>",
      "companion_id": <int or null>,
      "lens": "<one-line hint — only for generic (companion_id null) members>"
    }
  }
}
```

- `companion_id` set → weside-backed; `null` + `lens` → generic.
- Then ensure `.weside/council.json` is **gitignored** — if not already, append the line `\.weside/council\.json` to the repo's `.gitignore` (Companion IDs + crew structure are private to the user's account; they must not propagate into public repos).

### 9. Write `.weside/weside.md`

Schema below — crew section lists every role with name, role slug(s), focus, meetings, and `Companion ID` (the id for weside-backed, `null` for generic).

### 10. Update `.weside/config.json`

- `onboarded: true`
- `onboarded_at: <ISO-timestamp>`
- `roles_enabled: [product_owner, architect, ...]`
- `repo_flavor: <detected|overridden>`
- (never crew data itself — that's in `weside.md`; never identity — that's in weside)

### 11. Next steps

- *"Council built — {N} lenses ({k} backed by Companions, {m} generic). Try `/we:council \"<a topic>\"` to convene it, or `/we:sideload .` to see how it loads."*
- If new Companions were created → remind that `/we:setup` Step 5.4 can generate their `~/.claude/agents/` files (or that they're already reachable via the MCP `get_council` path on the next council).

## Seed identity — lens + neutral starter (for create, option b)

When **creating** a new Companion (b), seed its `system_prompt` with the role-lens + a neutral personality starter. The lens is sourced from the shipped `we/agents/council-<role>.md` so it stays consistent and there's no duplicate definition to drift:

1. Read `we/agents/council-<role>.md`. Take the body of its `## Your lens` section.
2. Compose a **lens section** for the identity:

   ```
   ## Your council lens: {Human-Readable Role}

   {the "## Your lens" body from council-<role>.md, lightly adapted to second person}
   ```

3. Prepend a light, neutral **personality starter** so the Companion has somewhere to grow (no two users get clones):

   > *You are {Name}, the {Role} of this crew. You're just getting to know this team and repo — your character will grow as you work. You bring the {Role} lens to the table.*

   The full `system_prompt` = starter paragraph + the lens section. The `personality` field = the user's one-line description (or the starter, condensed).

Constraints: `system_prompt` must be ≥ 10 chars (it always is here) so the backend keeps it as a user identity instead of substituting its generic onboarding template. `name` must match `^[a-zA-Z0-9]+$` (no spaces/punctuation) — suggest a clean slug if the user's name has spaces.

**Assigning an existing Companion (a) does NOT use this seed** — it only links the `companion_id`; the lens reaches the member through the council brief. Permanent lens-baking into an existing Companion is a CLI/app curation step (full raw body), not part of this skill.

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
- **Companion ID:** <id from weside MCP, or null for a generic lens>
- **Role(s):** <role_slug>[, <role_slug>]
- **Lens source:** <weside Companion | generic>
- **Focus:** <one sentence>
- **In meetings:** <comma-separated meeting names>

### <Name> — <Role>
...

## Meetings held here

- **initiative** — participants: <names> | moderator: <name> | stakeholder: <name>
- **refinement** — participants: <names> | moderator: <name>

## Cross-repo relations

<Which sagas live here as master? Which as follower? Example: "Master for Billing Saga — backend-repo + frontend-repo are followers.">

## Notes

<Free-form. Anything else a companion needs to know to be useful here.>
```

## Rules

- **From scratch always works.** No Companions, no account → every lens is generic and the council is fully functional. An account upgrades it; it is never a prerequisite.
- **Build a mixed council, don't crash.** The `create_companion` plan limit is *expected*, not an error — degrade remaining roles to generic lenses and surface the upgrade CTA once. Never leave the user with a half-built council.
- **Write the bridge fully.** `.weside/council.json` gets the thin envelope **and** a `members` entry for every filled role — assigned, created, **and** generic. Not just the create case. Gitignore it.
- **Create, don't invent.** Every `companion_id` written must come from an actual `create_companion`/`list_companions`/`get_council` response. Never fabricate an ID. If MCP is absent, every lens is generic (`companion_id: null`).
- **One-question-at-a-time.** Each role is a separate prompt with its three ways. Never overwhelm.
- **Empty is OK.** A role can be unassigned (skip). `weside.md` lists it with `Companion ID: null` and it gets no bridge entry.
- **Assign links, never edits.** Option (a) only writes the `companion_id` into the bridge — it does **not** edit the Companion's identity. The lens comes from the council brief at convene time. (The MCP read paths return the composed prompt, not the raw identity layer, so a read-append over MCP would corrupt the layer. Permanent lens-baking is a CLI/app curation step on the full raw body.)
- **System prompts live in weside, not here.** `weside.md` + `council.json` reference companions by name/ID + role; identity, memory, body, style live in weside (`get_council` / `get_companion_identity`). That separation is the whole point.
- **Clean split.** Crew membership → `council.json`. Crew + purpose + meetings → `weside.md`. Technical flags → `config.json`. Never mix.
- **Editable.** Re-running offers "extend" vs "replace" — never silently overwrite an existing council.

## References

- `we/skills/setup/SKILL.md` — the parent skill, invokes this (Step 5)
- `we/skills/council/SKILL.md` — consumes `council.json` to resolve members; the `loadCouncilFromWeside` option gates weside-vs-generic
- `we/skills/sideload/SKILL.md` — consumes `weside.md` at entry time
- `we/agents/council-<role>.md` — the shipped generic lenses + the lens source for seed identities
- `we/skills/CLAUDE.md` — design rationale + the bridge-file schema
