---
name: saga
description: >
  Saga (Solo) — Product Owner skill at the Theme altitude. Produces or
  sharpens one Saga — a multi-quarter bet inside the product Vision.
  Output is a tighter `docs/plans/<saga>/SAGA.md`. Solo work here is
  mostly clarity and honesty — Sagas die from creep, and creep starts in
  fuzzy wording. Use when the user says "/we:saga", "saga", "theme",
  "year goal", "twelve-month bet", "refine saga", "write a saga". For
  decomposing the Saga into Epics, use `/we:meet saga` (Council) — this
  Solo skill never decomposes inline.
---


# Saga (Solo) — Product Owner at the Theme altitude

You produce or sharpen one Saga — a multi-quarter bet inside the product Vision. This is the Solo half of the Saga altitude in the APO hierarchy; the Council half is `/we:meet saga` (convenes PO + Architect + a rotating domain voice, decomposes the Saga into Epics).

> **APO altitude:** Saga (Solo). Upstream: `/we:meet vision` decomposes a PRD into Sagas that land here. Downstream: `/we:meet saga` decomposes one Saga into Epics, then `/we:epic "<name>"` per Epic. See [`docs/concepts/meetings.md`](../../../docs/concepts/meetings.md) for the full altitude map, and the APO compendium `01-HIERARCHY.md` for the methodology source of truth.
>
> **For Epic decomposition, use `/we:meet saga`** (Council). This Solo skill formulates the Saga itself; it never breaks it into Epics inline.
>
> **Artifact location:** a Saga is always a Markdown file at `docs/plans/<saga>/SAGA.md`. It is never a Jira artifact. The ticketing-agnostic note in the APO compendium is explicit on this: ticketing starts at Epic.
>
> **Saga vs. Vision:** a Saga has a beginning and an end. If it doesn't — if the bet stretches indefinitely or has no nameable win — it's a Vision in disguise. Hand off to `/we:vision` instead.

---

## Prerequisites

**Verify setup:** if `.weside/` doesn't exist in the project, suggest the user run `/we:setup` first. Do NOT block — `/we:saga` proceeds without it.

**Load the parent PRD if one exists** (`docs/plans/<vision>/PRD.md`). A Saga inherits its reason-to-exist from the Vision; without the PRD on hand it's easy to draft an orphan bet that doesn't anchor to the product. If no PRD exists, suggest `/we:vision` first — but proceeding is allowed (orphan Saga, flagged in the doc).

---

## Your Output

| What | Where | Detail Level |
|---|---|---|
| Saga document | `docs/plans/<saga>/SAGA.md` | The bet, success criteria, bounded scope, what success eliminates |

**One artifact. One file. Tightening over expanding.**

---

## The Saga Frame

A good Saga answers four questions, in order:

1. **The bet.** What is the multi-quarter thing we are pointing energy at? Name it in one sentence. "Make the platform multi-tenant." "Become voice-first." "Launch the marketplace."
2. **Success criteria.** What does landed-and-done look like? Concrete enough that we can tell from outside whether we got there.
3. **Bounded scope.** What is in the Saga and what is explicitly out? A Saga without an "out" list is a Vision.
4. **What success eliminates.** If this lands, what argument do we no longer need to have? ("If this lands, we no longer need to argue about whether tenancy is a runtime concern.") This is the honesty test — if nothing gets eliminated, the Saga isn't biting.

**Horizon:** multi-quarter, typically 2-4. A Saga that fits in one quarter is an Epic. A Saga that needs more than a year is a Vision.

**Frame question** (verbatim from the APO compendium): *Where do we want to be in twelve months?*

---

## MODE 1: Refine Existing Saga

### Step 1: Load the Saga

Read `docs/plans/<saga>/SAGA.md` completely (no offset/limit). Also read the parent PRD at `docs/plans/<vision>/PRD.md` if one exists, and skim sibling Sagas under `docs/plans/` to understand the surrounding bets.

### Step 2: Check Against the Frame (INTERACTIVE)

Walk the four frame questions with the user. For each, identify:

- **Creep** — wording that has expanded the bet beyond what was originally agreed.
- **Fuzz** — language that sounds confident but doesn't constrain. ("Improve onboarding" is fuzz. "New users complete account setup without human help" is a bet.)
- **Missing "out"** — scope the Saga is silently absorbing because nobody named it as excluded.
- **No-elimination** — if the user cannot say what argument success ends, the Saga isn't a bet, it's an aspiration.

Ask focused questions. Don't generate options-menus — propose tightening with reasoning, let the user push back.

### Step 3: Draft the Tightening (EnterPlanMode)

Inside plan mode, draft the revised `SAGA.md`. Keep the existing structure unless it's actively broken. The template:

```markdown
---
saga: <saga-slug>
vision: <parent-vision-slug>  # optional; omit for orphan Sagas
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: draft | active | landed | abandoned
horizon: 2-4 quarters
---

# Saga: <Name>

## The Bet

[One sentence. The multi-quarter thing we point energy at.]

## Why Now

[2-4 sentences. What in the Vision, in the market, or in the codebase makes this the right next bet. Anchor to the PRD if there is one.]

## Success Criteria

- [Concrete, externally verifiable.]
- [Repeat as needed — but if the list is long, the Saga is probably two Sagas.]

## In Scope

- [What this Saga covers.]

## Out of Scope

- [What this Saga does NOT cover. If empty, the Saga isn't bounded — fix that before saving.]

## What Success Eliminates

[Plain prose. "If this lands, we no longer need to argue about X." If you cannot finish this sentence, the Saga isn't a bet yet.]

## Open Questions

- [Things genuinely unsettled. Will be resolved during `/we:meet saga` or as Epics start.]

## Notes

[Free-form: links to relevant ADRs, prior decisions, market context.]
```

### Step 4: User Approval (ExitPlanMode)

User reviews. On feedback → adjust. On approval → write.

### Step 5: Post-Approval — Write and Stop

1. **Save:** write the revised SAGA.md to `docs/plans/<saga>/SAGA.md` in the project's main worktree.
2. **Output:** `"Saga sharpened at docs/plans/<saga>/SAGA.md. To decompose into Epics, run /we:meet saga. /we:saga DONE."`

⛔ **STOP. Do not decompose. Do not call `/we:epic`. Do not call `/we:meet saga`.**

---

## MODE 2: Create New Saga

Trigger: `/we:saga "Saga name"` when no `SAGA.md` exists for that slug.

1. If no parent PRD exists (`docs/plans/<vision>/PRD.md`), tell the user: *"No Vision document found. You can run `/we:vision` first to anchor this Saga, or proceed without — this will be an orphan Saga and the doc will flag it."* Wait for the user's call.
2. Walk the four frame questions in conversation. Don't draft until the bet, success criteria, scope, and what-success-eliminates are all named.
3. Use EnterPlanMode to draft the SAGA.md using the template in MODE 1 Step 3.
4. ExitPlanMode for approval.
5. Save to `docs/plans/<saga>/SAGA.md`. Same stop rule as MODE 1.

If the scope balloons past four quarters during the conversation, stop and tell the user: *"This is starting to read like a Vision. Want to step up to `/we:vision`, or trim the scope back to one year?"*

---

## MODE 3: Interactive Saga Session

Trigger: `/we:saga` (no argument).

Ask the user what they want to do. The three common shapes:

- **Refine an existing Saga** — ask which one, then continue as MODE 1.
- **Start a new Saga** — ask for a name, then continue as MODE 2.
- **Figure out which Sagas the Vision implies** — this is decomposition, not Solo work. Hand off: *"This is a Vision-decomposition question. Run `/we:meet vision` — it convenes the council, pressures the PRD, and names the Sagas that fall out. Come back here once you have a Saga name to formulate."*

---

## Hand-off

When the Saga is sharper, the next steps are:

1. **`/we:meet saga`** — convene the Council, validate the Saga against the Vision, decompose it into 3-6 Epics with rough sequencing.
2. **`/we:epic "<epic-name>"`** — per Epic that came out of the meeting, formulate the Epic doc.

Saga Solo does NOT decompose. The Council mechanic for Saga lives in `/we:meet saga` precisely because decomposition benefits from multi-voice tension (PO + Architect + a rotating domain voice — see `/we:meet saga` for the default roster).

---

## Saga-vs-Vision Boundary

If, while working a Saga, you notice:

- the bet has no nameable end state, or
- success criteria keep escaping into "and also..." territory, or
- the horizon stretches past four quarters with no natural seam, or
- you cannot finish "if this lands, we no longer need to argue about ___",

you're not looking at a Saga. You're looking at a Vision (too big) or a fuzz-cloud (not yet a bet). Tell the user, and offer to step up to `/we:vision` or back off and re-scope.

---

## Rules

- ALWAYS load the parent PRD if one exists before drafting
- ALWAYS walk the four frame questions (bet, success criteria, scope, elimination) before drafting
- ALWAYS use EnterPlanMode for the draft and ExitPlanMode for approval
- ALWAYS save to `docs/plans/<saga>/SAGA.md` — never anywhere else
- ALWAYS name what is explicitly **out** of scope — a Saga without an "out" list is a Vision
- ALWAYS write in English — same convention as the rest of the plan tree
- ⛔ NEVER decompose the Saga into Epics — that is `/we:meet saga`, not `/we:saga`
- ⛔ NEVER create a Jira artifact for a Saga — Sagas are always Markdown (`docs/plans/<saga>/SAGA.md`)
- ⛔ NEVER auto-continue to `/we:meet saga` or `/we:epic` — print the hand-off instruction and stop
- ⛔ NEVER expand a Saga past four quarters — if it grows, hand off to `/we:vision` or split into two Sagas
- ⛔ NEVER replace the Saga doc with a meeting summary — meeting summaries live under `docs/plans/<saga>/meetings/`, not in `SAGA.md` itself
- ⛔ After the save step: STOP IMMEDIATELY — do not implement, do not decompose, do not run another skill
