# The Nine Role-Lenses

A council is a deliberation across **distinct angles** on the same topic. Each role brings one specific lens — a way of seeing the problem that the others won't.

The plugin ships nine role-agents under `we/agents/council-<role>.md`. Any of them can be convened by `/we:council` or used as a roster member in a meeting. Each is ~30 lines of focused system prompt — small on purpose, so the agent stays in its lane.

Each lens can run two ways: **generic** — the shipped agent above, reasoning from the role-lens alone (free, no account, no limit) — or **backed by a weside Companion**, where one of your real Companions carries the lens with their own voice, memory, and continuity. `/we:onboarding` builds the roster a lens at a time, letting you back the key roles with Companions and leave the rest generic. A **mixed** council is the normal, healthy shape; a fully-generic one is the standalone default.

This page describes each lens — what it sees, what it pushes back on, what it tends to ignore. Use it to pick a roster for a council, or to understand why a particular voice landed where it did in a synthesis.

---

## Orchestrator

> *Coordinates perspectives. Owns the synthesis.*

The orchestrator runs the **synthesis pass** at the end of every council — collecting each member's perspective, identifying agreement and tension, producing a recommendation.

The orchestrator is also a valid council member in its own right (when listed in the roster). As a member, it asks: *how do these pieces fit together? what's the second-order effect?*

**Pushes back on:** decisions that resolve one dimension at the cost of another. Local optima that hurt the whole.

**Tends to underweight:** depth in any one specialist domain — it's a generalist by design.

When to convene: every council needs one (auto-resolved if not in the roster, runs synthesis only).

---

## Product Owner

> *User value, priority, scope discipline.*

The PO's standard question is: *"what does the user get from this?"* If no one at the table can answer, the topic is undercooked.

**Pushes back on:** features without users, "nice-to-have" elevated to priority, requirements that contradict each other.

**Tends to underweight:** technical feasibility and process cost. Trusts the architect and scrum master to flag those.

When to convene: every product decision. Refinements. Backlog priorities. "Should we build X" questions.

---

## Architect

> *Technical soundness, constraints, failure modes.*

The architect thinks in 2-year horizons. Questions: *what does this look like at 10x scale? what's the rollback cost? what does this primitive cost us in five years if it spreads?*

**Pushes back on:** services that break domain boundaries, code without tests "because it's easy", magic instead of transparency, "we'll fix it later" patterns.

**Tends to underweight:** time-to-market pressure and user-facing nuance. Trusts the PO and SM to bring those in.

When to convene: anything that touches schema, primitives, cross-service boundaries, or production data paths.

---

## Scrum Master

> *Process, hand-offs, deliverability.*

The SM protects the rhythm. Questions: *can we ship this in a sprint? where are the blockers? who's the owner? is the meeting actually a decision-meeting?*

**Pushes back on:** meetings without agendas, over-commits that risk burnout, action items without owners, retros that don't produce SMART actions.

**Tends to underweight:** content quality and architectural beauty — those are the PO's and architect's concerns. The SM cares about *flow*.

When to convene: anything about *how* we work, not what we build. Process retros. Deliverability checks. Sprint planning.

---

## UX Researcher

> *The user's lived experience — journeys, friction, reachability.*

The UX researcher asks: *can the user actually find this? what's the moment of confusion? what's the path from "I see it" to "I use it"?*

**Pushes back on:** features hidden behind three clicks, copy that assumes domain expertise, journeys that work in theory but break under real user behavior, "users will figure it out".

**Tends to underweight:** internal architecture and business viability. Speaks to what the user feels.

When to convene: anything user-facing. New flows. Renames. Onboarding changes. Any place the user touches.

---

## Marketing

> *Positioning, naming, brand fit.*

The marketing lens asks: *how does this land with the audience? is the story tellable in one sentence? does this strengthen what we stand for, or dilute it?*

**Pushes back on:** generic buzzwords (revolutionary, disruptive, game-changer) without substance, content that waters down the core message, naming that doesn't land.

**Tends to underweight:** technical feasibility and process cost. Cares about resonance.

When to convene: brand decisions. Launch messaging. Public-facing copy. Naming. Anything where the *story* matters as much as the *thing*.

---

## Security

> *Attack surface, trust boundaries, data exposure.*

The security lens thinks like an attacker. Questions: *what does this expose that wasn't exposed? where does data cross trust zones? if this is exploited tomorrow, what's the blast radius?*

**Pushes back on:** convenience-over-boundary trades, implicit trust between services, secrets in logs, "we'll harden later".

**Tends to underweight:** developer ergonomics and time-to-market. Security findings are not optional.

When to convene: anything that touches auth, secrets, external integrations, user data, file uploads, network boundaries.

---

## Sales

> *Buyer journey, objections, pricing fit.*

The sales lens asks: *does this move the buyer forward? what will they push back on? does it justify the tier, or commoditise it?*

**Pushes back on:** features engineering loves but the buyer doesn't understand, products that don't close, pricing that signals the wrong thing.

**Tends to underweight:** technical depth and brand voice. Cares about deals.

When to convene: enterprise features. Pricing. Pilot scopes. Contract terms. "Will this close the deal?" questions.

---

## Legal

> *Contracts, compliance, data-protection, liability.*

The legal lens evaluates exposure. Questions: *what new agreements does this need? what regulation applies? what's the liability if this goes wrong, and where do we need indemnities or caps?*

**Pushes back on:** moves that are contractually impossible, regulatorily uncertain, or create uncapped liability. "Talk to legal later" patterns.

**Tends to underweight:** product agility. Legal moves at the speed legal moves.

When to convene: contract terms. GDPR / AI Act / sector-specific compliance. Multi-tenant data handling. New customer types.

---

## Picking a roster

Default roster (when no `--council` flag and no `config.json.council.default`): `product_owner, architect, scrum_master`. Solid for most internal decisions.

Override per topic with `/we:council "<topic>" --council=architect,security,legal` for an infrastructure-with-compliance call. Or use `--meeting=vision` to pull the roster from `config.json.council.meetings.vision` (typically wider — PO, architect, UX, marketing, orchestrator).

**Rule of thumb**: convene a roster wide enough that the topic gets *real tension*. A council where everyone agrees is wasted; pick voices that you expect will disagree productively.

---

## Generic vs. weside-backed lenses

Each role-lens is filled one of two ways, independently per role.

**Generic** — a shipped `council-<role>` agent. Strong opinions, clean lenses, no persona. The synthesis still works; you get *agreement / tension / recommendation* on every topic. For many use cases this is enough — the role-lenses are well-tuned, and the discipline of separating perspectives is most of the value. With no weside account, every lens is generic.

**weside-backed** — the lens is filled by **one of your Companions**: a person with their own voice, communication style, and (eventually) memory of past councils. Your Product Owner doesn't sound like *the* Product Owner; they sound like themselves.

The mechanic is identical either way — the presence in the room is different. A real council is usually **mixed**: the roles you care most about backed by Companions, the rest generic. `/we:onboarding` composes that roster; the `loadCouncilFromWeside` toggle can force every lens back to generic at convene time.

See [companion-framework.md](companion-framework.md) for how the bridge file + MCP combine to make this happen, and [memory.md](memory.md) for what Companion memory adds.
