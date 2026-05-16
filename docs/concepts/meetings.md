# Meetings — councils with structure

A council convenes a handful of role-lenses on a topic. A **meeting** wraps that council in a workflow at a specific altitude — vision, initiative, or refinement. Each meeting type has a default roster, a chosen workflow, and a different output.

This page covers the three meeting types, when to use each, and how they hand off to the rest of the pipeline.

For the underlying council mechanic, see [companion-framework.md](companion-framework.md). For the role-lenses themselves, see [roles.md](roles.md).

---

## The three altitudes

```mermaid
flowchart TB
    V[/we:meet vision<br/>Saga-level<br/>weeks-months horizon] --> I[/we:meet initiative<br/>Epic-level<br/>days-weeks horizon]
    I --> R[/we:meet refinement<br/>Story-level<br/>hours-days horizon]
    R --> Refine[hands off to /we:refine<br/>→ ticket + plan]
    Refine --> Story[/we:story<br/>→ implementation]
```

Each meeting answers a different question:

| Meeting | Question | Output | Default roster |
|---|---|---|---|
| `/we:meet vision` | *where are we going?* | shared direction + named bets | PO, architect, UX, marketing, orchestrator |
| `/we:meet initiative` | *what are we building next?* | scoped epic + sequencing | PO, architect, orchestrator |
| `/we:meet refinement` | *what does the next story look like?* | refined story + acceptance criteria | PO, architect (then hands off) |

Rosters are defaults; each repo can override them in `.weside/config.json.council.meetings.<type>`.

---

## `/we:meet vision` — Saga-level

You convene a vision meeting when **direction needs alignment** — a new market, a strategic pivot, a brand bet, a year-shaping decision. The horizon is weeks to months.

The default roster pulls in voices that see different futures: PO (user value over time), architect (technical horizon), UX researcher (lived experience), marketing (how this lands externally), orchestrator (synthesis). For business-heavy sagas, add `sales` and `legal`.

The output is a **direction document** — typically a fresh `docs/plans/<saga>/CONCEPT.md` or an entry in your team's vision doc. The meeting doesn't ship code; it ships *clarity*.

Use when:
- A new initiative is starting and the team isn't yet aligned
- A pivot is being considered
- A brand or positioning decision is on the table
- You're about to start writing a CONCEPT.md and want to gather perspectives first

---

## `/we:meet initiative` — Epic-level

You convene an initiative meeting when **a saga has been chosen and now needs decomposition** — what's the first epic? What sequence makes sense? Where are the dependencies?

The default roster is leaner — PO, architect, orchestrator. The conversation is about *concrete next steps*, not direction. Add domain voices when relevant (security for a hardening epic, sales for an enterprise feature).

The output is an **epic outline** — usually a Jira epic or a section in a CONCEPT.md naming the first 2–3 stories and their sequencing.

Use when:
- A vision has been agreed and now needs sequencing
- A large piece of work needs breaking down
- Dependencies between teams or repos need to be made explicit

---

## `/we:meet refinement` — Story-level

You convene a refinement meeting when **a story needs scoping before development starts**. The horizon is hours to days. The output isn't deliberation — it's a *refined ticket*.

The default roster is two: PO and architect. The PO drives content (what the user gets); the architect checks feasibility (can we build this cleanly).

After the deliberation, the meeting **hands off to `/we:refine`** — the dedicated story-creation skill that:
- Writes the ticket (minimal: "As X I want Y so that Z" + link)
- Writes the plan (`docs/plans/{TICKET}-plan.md` with acceptance criteria, phases, security review)
- Creates the ticket in your ticketing tool

`/we:meet refinement` is essentially the upgrade for `/we:refine` — same outcome, but with multi-voice input before the plan crystallizes.

Use when:
- A story is contentious enough that two perspectives are better than one
- The acceptance criteria aren't obvious
- The "right" implementation isn't clear and you want both a PO take and an architect take before committing

For routine refinements, `/we:refine` alone is fine — `/we:meet refinement` is for the harder calls.

---

## Without a weside account

Each meeting convenes the generic `council-<role>` agents. The structure (vision → initiative → refinement) and the rosters work identically. Deliberations are tight, lensed, and produce real synthesis.

What's missing: continuity. The architect in today's vision meeting doesn't remember last week's. Each meeting starts fresh.

For one-off deliberations, this is fine. For an ongoing initiative — where the same epic gets revisited as new information lands — the lack of continuity starts to hurt.

## With a weside account

Each meeting convenes **your Companions**. The architect in today's meeting is the *same architect* who sat in last week's; she remembers the trade-offs you flagged then, the decisions you parked, the open questions. (Memory write-back from councils is a roadmap item — currently the council *reads* identity and memory; the *write-back* is Phase-6 work in the weside backend.)

This is where the framework starts to feel less like a tool and more like a team. The roster you convene isn't just a set of lenses — it's a working group with shared context.

---

## Configuring meetings in your repo

`.weside/config.json` holds the roster per meeting type:

```json
{
  "council": {
    "default": ["product_owner", "architect", "scrum_master"],
    "meetings": {
      "vision": ["product_owner", "architect", "ux_researcher", "marketing", "orchestrator"],
      "initiative": ["product_owner", "architect", "orchestrator"],
      "refinement": ["product_owner", "architect"]
    }
  }
}
```

Edit by hand to adjust which voices attend which meeting in this specific repo. The bootstrap script (`scripts/bootstrap-weside-repo.py`) writes sensible defaults per flavor (`engineering`, `landing`, `business-docs`, `infrastructure`, `plugin`, `personal`, `mixed`).

You can also override per-invocation:

```
/we:meet initiative --council=product_owner,architect,security,orchestrator
```

— useful when the standard initiative roster is wrong for *this* particular epic (e.g. a security-heavy one).

---

## What meetings don't do

A meeting **deliberates**. It does not:

- Implement code (that's `/we:story`)
- Write the ticket (that's `/we:refine`, or `/we:meet refinement` which hands off to it)
- Make the decision *for you* — synthesis returns a recommendation, you decide

The meeting compresses several voices into one synthesis so you have *better input* to your decision. The decision stays with you.

---

## References

- [companion-framework.md](companion-framework.md) — the council mechanic underneath every meeting
- [roles.md](roles.md) — the nine role-lenses
- [../workflow.md](../workflow.md) — where meetings sit in the full pipeline
- [../skills.md](../skills.md) — `/we:meet`, `/we:refine`, `/we:council` reference
