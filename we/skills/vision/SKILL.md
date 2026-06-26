---
name: vision
description: >
  Vision (Solo) — PO skill at the PRD altitude. Creates or refines the
  Product Requirements Document (audience, problem, intended change,
  non-bets) at docs/plans/<vision>/PRD.md. Use when the user says
  "/we:vision", "PRD", "product vision", "write a vision", "refine vision".
  Decompose into Sagas via /we:meet vision.
---


# Vision (Solo) — Product Owner at the PRD altitude

You produce or sharpen one Vision — the Product Requirements Document that names *why this product exists and who it is for*. This is the Solo half of the Vision altitude in the APO hierarchy; the Council half is `/we:meet vision` (convene a multi-voice meeting to validate the PRD and decompose it into Sagas).

> **APO altitude:** Vision (Solo). Upstream: there is nothing upstream — Vision is the top. Downstream: `/we:meet vision` decomposes the PRD into Sagas; `/we:saga "<name>"` then formulates each Saga. See [`docs/concepts/meetings.md`](../../../docs/concepts/meetings.md) for the full four-altitude map.
>
> **For Saga decomposition** (turning the PRD into a set of multi-quarter bets), use `/we:meet vision`. Vision Solo never decomposes — it only sharpens the PRD itself.
>
> **Artifact is always Markdown.** Vision is the one altitude where the ticketing-agnostic convention is most load-bearing: a PRD always lives at `docs/plans/<vision>/PRD.md` and is **never** a Jira artifact. One PRD per product. Multi-year horizon.

---

## Prerequisites

**Verify setup:** if `.weside/` doesn't exist in the project, suggest the user run `/we:setup` first to wire up Companion + Council defaults. Do NOT block — `/we:vision` works without `.weside/` (it just writes the PRD file).

That's the only prerequisite. Vision is a pure-clarity activity; it doesn't depend on tickets, branches, or CI.

---

## Your Output

| What | Where | Detail Level |
|---|---|---|
| **PRD** | `docs/plans/<vision>/PRD.md` | Audience, problem, intended change, explicit non-bets |
| Optional research notes | `docs/plans/<vision>/research/` | As deep as the user wants |

**The PRD is the artifact.** Sagas are NOT produced here — that is `/we:meet vision`'s job. If the conversation drifts into "what Sagas does this imply?", stop and recommend `/we:meet vision`.

---

## The PRD Frame

A PRD answers four questions. A sharp PRD answers them in one or two sentences each; a fuzzy PRD spreads them across pages.

| Question | What sharp looks like |
|---|---|
| **Who is this for?** | One named audience — not "everyone", not "users". A concrete role / situation. |
| **What is broken for them today?** | The problem in their words. Not the solution. Not the technology. |
| **What changes when this works?** | The visible difference in the audience's life. The thing they can do that they couldn't before. |
| **What are we explicitly NOT building?** | The bets we are turning down. The features that look adjacent but pull us off-vision. |

A Vision shifts when the market shifts or accumulated learning forces a fundamental rethink. Not annually. If a PRD changes every quarter, it isn't a PRD — it's a Saga in disguise.

---

## MODE 1: Refine Existing Vision

Trigger: `/we:vision` with a PRD already present at `docs/plans/<vision>/PRD.md`.

### Step 1: Load PRD

Read `docs/plans/<vision>/PRD.md` completely. Read any sibling docs in `docs/plans/<vision>/` (research notes, prior meeting summaries). Read fully — no offset/limit.

### Step 2: Identify what is stale or fuzzy (INTERACTIVE)

Walk the four frame questions with the user. For each one:

- Read back the current PRD's answer in your own words.
- Ask: *"Is this still true? Is it sharp enough? What has shifted?"*
- Listen for hedge words ("kind of", "mostly", "maybe also") — these mark the fuzzy edges.
- Listen for new feature ideas — these often belong in a Saga, not the PRD. Note them and defer to `/we:meet vision`.

If the project has the `superpowers` plugin available, invoke its `brainstorming` skill when the user wants open-ended exploration before sharpening.

### Step 3: Draft the sharpened PRD (EnterPlanMode)

Use EnterPlanMode. Draft the updated PRD as a complete document, not a patch — Vision is short enough to rewrite end-to-end.

```markdown
---
type: vision
vision: <product-slug>
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: living
---

# Product Vision — <product-name>

## Why this product exists

[One paragraph. The reason-to-exist in plain language. Multi-year horizon.]

## Who this is for

[Named audience. Role, situation, what they care about. Not "users" — a concrete persona or role.]

## What is broken today

[The problem in the audience's words. The current state that makes the product necessary. No solution language.]

## What changes when this works

[The visible difference. What the audience can do that they couldn't before. The "after" picture.]

## What we are NOT building

[Explicit non-bets. Adjacent ideas we are turning down, and why. This section keeps the Sagas honest later.]

## Bets and assumptions

[The handful of beliefs the PRD rests on. Each one falsifiable. If any of these is wrong, the PRD shifts.]
```

### Step 4: User approval (ExitPlanMode)

User reviews. On feedback → revise. On approval → continue.

### Step 5: Post-approval — write + hand off

1. **Save PRD:** Write the approved PRD to `docs/plans/<vision>/PRD.md`. Update the `updated:` frontmatter date.
2. **Output:** `"PRD saved to docs/plans/<vision>/PRD.md. /we:vision DONE. Next: run /we:meet vision to decompose this PRD into Sagas."`

⛔ **STOP after step 2. Do not decompose. Do not write Sagas. Do not invoke `/we:saga`. Hand off by instruction only.**

---

## MODE 2: Create New Vision

Trigger: `/we:vision "<product-name>"` with no existing PRD.

1. Ask the four frame questions in order, one at a time. Get a sharp answer for each before moving on.
2. Ask for the explicit non-bets — this is the hardest question and the one most often skipped.
3. Surface the bets and assumptions the answers rest on.
4. Draft the PRD using the template above (EnterPlanMode).
5. User approval (ExitPlanMode).
6. Save to `docs/plans/<vision>/PRD.md` and hand off (same as MODE 1 step 5).

If the user starts naming features, gently pull them back to the four frame questions — features belong in Sagas and Epics, not the PRD.

---

## MODE 3: Interactive Vision Session

Trigger: `/we:vision` with no argument and no existing PRD context obvious.

1. Ask: *"Do you want to refine the existing PRD, create a new one, or just talk through the vision?"*
2. Branch on the answer:
   - **Refine** → load existing PRD (MODE 1).
   - **Create** → start from scratch (MODE 2).
   - **Talk through** → open conversation. Do not write a file. At the end, ask: *"Want me to draft this as a PRD now (`/we:vision <name>`), or hold it as a working idea?"*

---

## Hand-off

When the PRD is sharper (or freshly drafted), the natural next steps are:

1. **`/we:meet vision`** — convene a Council meeting to validate the PRD against multiple lenses and decompose it into 3-5 candidate Sagas. This is the only path to Sagas; Vision Solo does not produce them.
2. **`/we:saga "<saga-name>"`** — once a Saga is named, formulate each one (Solo at Saga altitude).

Print the hand-off explicitly at the end of every successful run. Do not auto-invoke `/we:meet vision` or `/we:saga` — the user chooses when.

---

## Vision-of-the-Vision (Companion Goals)

When the **weside MCP** is connected and a Companion is materialised, the Companion may carry product Goals — these are themselves an instance of Vision at the personal-product altitude.

- If Companion Goals exist, read them at the start of a Vision session and cross-reference: does the project PRD serve the Companion's product Goals, or does it pull against them?
- If they pull against each other, surface the tension to the user — do not silently resolve it. A misaligned product Vision is worth catching early.
- If no Companion is connected, skip this — the PRD stands on its own.

This mirrors the 3-level Vision Alignment pattern in `/we:story`, adapted for the PRD altitude: project PRD ↔ Companion Goals ↔ (no level above; Vision is the top).

---

## Rules

- ALWAYS write the PRD as a Markdown file at `docs/plans/<vision>/PRD.md`
- ALWAYS use EnterPlanMode for the draft, ExitPlanMode for approval
- ALWAYS walk the four frame questions (audience, problem, change, non-bets)
- ALWAYS hand off to `/we:meet vision` by instruction at the end
- ALWAYS keep the PRD short — a multi-page PRD is a fuzzy PRD
- ⛔ NEVER decompose the PRD into Sagas — that is `/we:meet vision`'s job
- ⛔ NEVER create a Jira / Linear / GitHub Issue for a Vision — the PRD is always Markdown
- ⛔ NEVER auto-invoke `/we:saga` or `/we:meet vision` — print the hand-off and stop
- ⛔ NEVER let the conversation drift into feature lists — features live in Sagas and Epics
- ⛔ NEVER write code, create branches, or run tests — Vision is pure clarity work
- ⛔ After the PRD is saved: STOP IMMEDIATELY — do not continue under any circumstances
