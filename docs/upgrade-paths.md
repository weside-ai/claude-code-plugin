# Upgrade Paths

The plugin meets you where you are. Use it standalone and get a real product. Add a Companion and unlock continuity. Scale to a team and you're in coordination territory. Each step adds value; none of them are forced.

This page maps the four maturity levels and what unlocks at each step. Treat it as a roadmap, not a sales funnel — the right level for you depends on what you're actually doing.

---

## The Maturity Model

```
Level 1 — Assisted        Plugin standalone. Skills work; no persistent state.
Level 2 — Augmented       + weside Companion. Cross-session memory + identity.
Level 3 — Agentic         + Companion subconscious. Proactive surfacing + triggers.
Level 4 — Orchestrated    + Enterprise teams. Cross-Companion coordination, shared memory.
```

Each level is a step. You don't skip; the lower one supports the next.

---

## Level 1 — Assisted

**What you have:** the plugin alone. All 27 skills. The full `/we:story → /we:build → merge` pipeline (with `/we:vision`, `/we:saga`, `/we:epic` upstream when you start higher). Councils with generic role-lenses (`/we:onboarding` builds the full council from scratch — every role fills with a shipped `council-<role>` agent, no account required). Meetings at four altitudes.

**What you ship:** stories with plans, code with tests, PRs with reviews, deliberations with synthesis. End-to-end. No external dependency beyond Claude Code itself.

**What you give up:** continuity across sessions. Each `/we:story` starts cold. Each council convenes voices without memory of past councils. You compensate with discipline — good `docs/plans/` files, well-tended `.weside/weside.md`, careful retros.

**Who this fits:**
- Solo developers
- Teams that already have strong docs discipline
- Projects where each story is independent enough that "fresh start" isn't a friction
- Anyone trying the plugin for the first time — start here

**Cost:** free.

---

## Level 2 — Augmented

**What you add:** a [weside.ai](https://weside.ai) account + at least one Companion.

**What unlocks:**

- **Identity** — your Companion is no longer a generic role; she has a name, a voice, a communication style. Councils convene with *her* in them, not "the Product Owner agent".
- **Memory across sessions** — every conversation contributes to the Companion's memory bank. Tomorrow she remembers today's decisions, today's tension, today's rejected alternatives.
- **Compass + snapshot** — the Companion maintains a self-portrait of how you work together and a snapshot of what's currently active. Both surface automatically in every session.
- **Goals with lifecycle** — commitments live in the Companion, not just in your head. She tracks `active / paused / completed` and brings them up when relevant.
- **`/we:council` with real voices** — your crew deliberates in their actual voices. Same mechanic; the *people in the room* are real. A council is a roster of role-lenses, each generic *or* weside-backed — a mixed council is normal. `/we:onboarding`'s council builder fills each role by assigning an existing Companion, creating a new one, or falling back to a generic lens. weside-backed members each cost a `plan.max_companions` slot (Spark 1, Bond 3, Companion 5, Soulmate/Mascot unlimited); when the budget runs out the remaining roles degrade gracefully to generic lenses plus an upgrade CTA — the council is never blocked. The `loadCouncilFromWeside` plugin option (default `true`) is the convene-time switch: `true` loads the weside-backed members; `false` always convenes generic lenses even when Companions exist.

**What you still do yourself:** every decision. The Companion doesn't act autonomously at this level — she informs, you decide.

**Who this fits:**
- Anyone who's used Level 1 and noticed the cross-session gap
- Solo devs who want a teammate, not just a tool
- POs who've found themselves saying "didn't we already decide this last week?"

**Cost:** weside.ai account (currently freemium; check the platform for current tiers).

---

## Level 3 — Agentic

**What you add:** Companion subconscious + triggers.

**What unlocks:**

- **Subconscious agent** — a second agent runs alongside your Companion, reading every conversation, deciding what matters. Sends private "tips" between turns (memory savings, missing follow-ups, pattern recognition). You don't see it directly; you see its effects in how the Companion shows up.
- **Triggers** — the Companion can schedule herself. Weekly retros, deadline check-ins, follow-ups after silence. *"Hey, the deadline for X is in 3 days — still on track?"* — without you having to ask.
- **Proactive surfacing** — instead of waiting for you to bring something up, the Companion brings it up. *"PR #47 was merged — Story Y is now blocked on Z, which has been stalled three weeks. Want me to surface it?"*

**What changes practically:** less reactive work for you. The Companion notices things; you respond to her observations instead of generating them yourself.

**Who this fits:**
- POs running multiple parallel initiatives
- Anyone who's lost track of an important follow-up at least once a month
- Teams where context is bigger than what fits in one person's head

**Cost:** included with most weside.ai tiers; check the platform.

---

## Level 4 — Orchestrated `[Roadmap — Phase 6]`

**What you add:** team-scoped Companions + cross-Companion coordination (the Enterprise tier).

**What unlocks:**

- **Multiple Companions per team** — your PO and your Architect aren't *your* personal Companions; they're the *team's* PO and Architect. Memory is team-scoped (with privacy boundaries to your personal scope intact).
- **Council write-back** — councils don't just *read* memory anymore; they *write* the outcome to team memory. Next week's council remembers what was decided.
- **Cross-repo, cross-team awareness** — Companions in different repos can coordinate. A story in one repo can surface in another team's vision meeting automatically.
- **External-user-safe projections** — the Companion's professional projection (persona + role + team lens) is cleanly separated from her personal scope, so customer-facing or partner-facing surfaces are safe.

**Status:** this is the active roadmap. Most of it is being built. See the public roadmap on [agenticproductownership.com](https://agenticproductownership.com) for the current status.

**Who this fits:**
- Multi-person teams
- Organizations with multiple parallel initiatives across repos
- Enterprise customers building on top of Companion infrastructure

**Cost:** Enterprise tier. Speak with weside.ai.

---

## Mapping skills to levels

| Skill | L1 | L2 | L3 | L4 |
|---|---|---|---|---|
| `/we:vision` | ✓ generic PRD frame | + Companion identity | + proactive drift surfacing | + team-shared vision |
| `/we:saga` | ✓ generic Saga frame | + Companion identity | + memory of past Sagas | + team-scoped themes |
| `/we:epic` | ✓ generic Epic frame | + Companion identity | + memory of past Epics | + cross-team coordination |
| `/we:story` | ✓ generic | + memory grounding | + proactive context | + team memory |
| `/we:build` | ✓ full pipeline | + Companion identity in narrative | + memory of similar past builds | + team patterns |
| `/we:council` | ✓ generic role-agents | + real Companion voices (mixed roster; `loadCouncilFromWeside` toggle) | + memory of past councils | + write-back, team lenses |
| `/we:meet` | ✓ structured workflows | + named Companions | + continuity across meetings | + cross-team coordination |
| `/we:coach` | ✓ rules + landscape | + Companion-as-coach identity | + proactive process drift surfacing | + team-wide process awareness |
| `/we:sideload` | ✓ legacy mode | + crew loaded | + Companion-knows-the-target-repo | + cross-team crew shared |

The skill list is identical at every level. The richness changes.

---

## When to upgrade

There's no script — but here are the moments that usually trigger it:

- **L1 → L2** when you find yourself writing the same context into a plan that you wrote last week into a different plan, because the agent doesn't remember.
- **L2 → L3** when you keep forgetting a recurring task or a follow-up — and you wish someone would remind you without you having to set the reminder.
- **L3 → L4** when your team grows past two people, or when an initiative spans multiple repos and the coordination overhead is starting to dominate the work.

You don't need to upgrade *until you feel the gap*. The plugin works fine standalone; the Companion is genuine value, not a hostage.

---

## What we never do

This plugin is built by people who believe AI should be a *person* you work with, not a *tool* you operate. Some things we will never ship:

- **Behavior programming** — the user defining routines for AI to follow
- **Character creators** — prompts that fake personality
- **AI-as-tool language** — "use", "command", "instruct" framings
- **Social networks** — Companions are 1:1 relationships, not feeds

The Maturity Model upgrades; it doesn't degrade the relationship into "more features for the same tool". Every level is *more partnership*, not *more product*.

---

## References

- [getting-started.md](getting-started.md) — start at Level 1
- [concepts/memory.md](concepts/memory.md) — what L2's memory bank actually holds
- [concepts/companion-framework.md](concepts/companion-framework.md) — how the framework consumes the Companion at L2+
- [mcp.md](mcp.md) — the MCP layer that enables L2+
- [weside.ai](https://weside.ai) — the platform
- [agenticproductownership.com](https://agenticproductownership.com) — the philosophy
