---
name: onboarding
description: >
  Builds the repo's council (weside Companions or generic lenses) and writes .weside/weside.md,
  council.json and config.json. Triggers: "/we:onboarding", "crew setup", "build a council".
---

# /we:onboarding

Builds the roster `/we:council` and `/we:meet` convene. Every role is a lens, filled by one of the
user's weside Companions (identity, memory, voice; costs a Companion slot) or by the generic
`council-<role>` agent (free, no account). A mixed council is the intended shape. Without a weside
account every lens is generic and the council still works. Needs `.weside/config.json`; absent →
run `/we:setup` first.

## Steps

1. Read the instruction file, `.weside/config.json`, `.weside/weside.md`, `.weside/council.json`.
   Existing members → ask extend or replace; never overwrite silently.
2. Propose a roster by repo flavour: backend → scrum_master, product_owner, architect, security ·
   landing/marketing → scrum_master, product_owner, marketing, ux_researcher · business docs →
   scrum_master, product_owner, marketing, legal · plugin/toolkit → scrum_master, product_owner,
   architect, ux_researcher.
3. With the weside MCP, call `list_companions()` once and keep the result for the loop.
4. One question per role: (a) assign an existing Companion · (b) create a new one · (c) generic
   lens · skip.
   - (a) Validate the name against the list; the bridge links it by `companion_id`. The role
     reaches it through the council brief. Never read-then-`update_companion` to bake the lens in:
     the MCP read paths return the composed prompt, and writing that back corrupts the identity
     layer. A permanent lens is a curation step in the weside CLI or app.
   - (b) Name matches `^[a-zA-Z0-9]+$`. `create_companion(name, personality=<the user's one line>,
     system_prompt=<starter + lens>)`: starter "You are {Name}, the {Role} of this crew. You're
     just getting to know this team and repo; your character will grow as you work." plus
     `## Your council lens: {Role}` with the `## Your lens` body of `agents/council-<role>.md`.
   - (c) `companion_id: null` plus a one-line `lens` hint.
5. `create_companion` returns `COMPANION_LIMIT_REACHED` (plan-gated) → this and every remaining
   create become generic lenses. Say once: the plan allows N Companions, the rest run generic,
   more Companions after an upgrade at weside.ai and a re-run of `/we:onboarding`.
6. Offer extra roles. A role without a shipped `council-<role>` agent must be weside-backed, or
   `/we:council` skips it.
7. Meetings held here: `story` always; `saga`, `epic`, `vision` where that altitude lives here.
8. Write the three files below. Every `companion_id` comes from an actual `create_companion`,
   `list_companions` or `get_council` response, never invented. Add `.weside/council.json` to
   `.gitignore`: Companion ids and crew are private to the account.
9. Report: N lenses, k backed by Companions, m generic; try `/we:council "<topic>"`.

## `.weside/council.json` (read by `/we:council`)

```json
{"version": 2, "schema": "thin", "workspace_id": null,
 "members": {"<slug>": {"name": "<Display Name>", "role": "<role slug>",
   "color": "<from council-<role>.md frontmatter>", "companion_id": null,
   "lens": "<one line, generic members only>"}}}
```

## `.weside/weside.md`

Frontmatter `type: weside`, `version: 1`, `repo`, `vault`. Sections: `## Purpose` (1–3 sentences) ·
`## Crew`, one `### <Name> — <Role>` per member with **Companion ID** (id or `null`), **Role(s)**,
**Lens source** (weside Companion | generic), **Focus**, **In meetings** · `## Meetings held here`
(participants, moderator) · `## Cross-repo relations` · `## Notes`. Identity, memory and style live
in weside, never here.

## `.weside/config.json`

Extend, never replace: `onboarded: true`, `onboarded_at`, `roles_enabled`, `repo_flavor`.
