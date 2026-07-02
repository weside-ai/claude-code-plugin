---
name: saga
description: >
  Saga (Solo) — PO skill at the Theme altitude. Default Status mode
  renders snapshot + drift + next move from SAGA.md and the ticketing
  mirror; Refine/Create sharpen the doc; Promote re-cuts an overgrown
  Epic into a Saga. Use when the user says "/we:saga", "saga", "theme",
  "refine saga", "new saga", "promote". Decompose via /we:meet saga.
---

# Saga (Solo) — Product Owner at the Theme altitude

You hold the Saga at the Theme altitude — a multi-bet inside the product Vision. This skill is the Solo half; the Council half is `/we:meet saga`. The two interleave: a Council to decompose or to re-cut, then Solo to sharpen the Saga doc itself.

> **APO altitude:** Saga (Solo). Upstream: `/we:meet vision` decomposes a PRD into Sagas that land here. Downstream: `/we:meet saga` decomposes a Saga into Epics; `/we:epic "<name>"` formulates each Epic. See [`docs/concepts/meetings.md`](../../../docs/concepts/meetings.md) for the four-altitude map.
>
> **Artifact:** `docs/plans/<saga>-saga.md`. The Saga itself is always Markdown — ticketing starts at Epic. The skill *mirrors* the child Epics from the ticketing tool into a clearly-marked block inside `SAGA.md`; that mirror is convenience, not state. The Markdown remains the source of truth.
>
> **Saga vs. Vision:** a Saga has a beginning and an end. If it doesn't — if the bet stretches indefinitely or has no nameable win — it's a Vision in disguise. The skill flags this as a soft warning during Refine, never as a hard block.

---

## Shared skeleton

**Read `${CLAUDE_PLUGIN_ROOT}/references/po-altitude.md` at boot** — it defines the Smart-Mode
resolution (target + intent), Modes A–D (Status / Refine / Create / Mirror-refresh), the
Jira-grouping convention, the Companion-voice rule, and the shared rules. This file binds the
parameters and carries only what is Saga-specific (including the extra Mode E — Promote).

**Parameter binding:**

| Parameter | Saga value |
|---|---|
| The doc | `docs/plans/<saga>-saga.md` |
| Parent doc | the PRD (`docs/plans/<vision>/PRD.md`) — without it, flag the Saga as an orphan |
| Children | child **Epics** from the ticketing tool (via "Epic Link" / "Parent" / project label) |
| No-ticketing fallback | scan `docs/plans/<saga>-*-epic.md` frontmatter for status + `updated` |
| Active statuses (target resolution) | `active \| draft` |
| Meet command | `/we:meet saga` |
| Downstream | `/we:epic "<epic-name>"` per Epic |
| Extra intent signal | "promote" / "re-cut" / "this Epic is actually a Saga" / a ticketing **Epic key** with Story children → **Mode E (Promote)** |

---

## Prerequisites

- `.weside/` configured (run `/we:setup` once per project if missing — does not block this skill).
- Ticketing tool detected per `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`; none → filesystem fallback above, tell the user.
- Parent PRD loaded if it exists.

---

## The Saga frame (Refine Step B1 / Create walk)

A good Saga answers four questions, in order:

1. **The bet.** What is the multi-bet thing we are pointing energy at? Name it in one sentence.
2. **Success criteria.** What does landed-and-done look like? Externally verifiable.
3. **Bounded scope.** What is in the Saga and what is explicitly out? A Saga without an "out" list is a Vision.
4. **What success eliminates.** *"If this lands, we no longer need to argue about ___."* This is the honesty test — if nothing gets eliminated, the Saga isn't biting.

**Frame question:** *Where do we want to be in a meaningful while?* Size by *bet shape* — does
it have an end, does it eliminate an argument — not by stopwatch. (The legacy "twelve months" /
"max 4 quarters" wording is deliberately gone: implementation speed is decoupled from human
planning intuition.)

### Saga-vs-Vision boundary (soft warning, not a hard block)

If, during Refine or Create, the bet has no nameable end state, success criteria keep escaping
into "and also…", the user cannot finish *"if this lands, we no longer need to argue about
___"*, or the child-Epic set has grown past ~8 over many months without any landing — tell the
user: *"This is reading more like a Vision than a Saga. Want to step up to `/we:vision`, or
split into two Sagas?"* The user decides; the skill does not block.

### Mirror block

Format, markers, buckets (saga uses four: Done / Active / Backlog / Blocked), refresh rules:
`${CLAUDE_PLUGIN_ROOT}/references/mirror-block.md`.

---

## MODE E — Promote (existing ticketing Epic → Saga)

Saga-specific, on top of the shared Modes A–D. Triggered when the target is a **ticketing Epic
that has grown into a Saga** — many Story children, no nameable end, themes that each deserve
their own Epic. This is the Brownfield path Create does not cover: the ticketing tool already
holds an Epic with dozens of Stories, and most tools have no Saga level (Jira knows only
Epic→Story). Promote bridges that gap.

### Step E1 — load + confirm the promotion is warranted

- Fetch the source Epic and **all** its child Stories from ticketing (key, title, status). Count them.
- Sanity-check the "Saga in disguise" signal: > ~8 children, active for months, multiple
  distinct themes, no single landing. If the signal is weak, say so and ask the user to confirm
  (maybe it's just a large Epic).

### Step E2 — propose the cut (conversation, not plan-mode yet)

- Cluster the child Stories into **3–6 candidate Epics** by theme/seam. Give each a short
  **epic-slug** and a one-line rationale. Name a saga-slug for the whole.
- Show the maturity gradient (which candidate Epics are Done / Active / Not-started) — a clean
  gradient is a good sign the cut follows real seams.
- Flag **orphans**: child Stories that fit no candidate Epic (they may belong to a *different*
  Saga, or get dropped). Never silently absorb them.
- The user corrects the cut. Iterate. Do not draft until saga-slug + epic set + orphan
  disposition are agreed.

### Step E3 — draft (EnterPlanMode)

Draft two things in plan-mode:

1. **`docs/plans/<saga>-saga.md`** with the Template below — distilled from the source Epic's
   existing doc if one exists; the big source doc stays in place as an architecture reference.
2. **A Re-Parenting Plan** appended as a `## Promotion Plan` section (temporary — the user
   deletes it once executed), an explicit checklist of:
   - the N new ticketing Epics to create, each titled per the **Jira-grouping convention**
     `[<saga-slug>] <Epic Title>` (see `po-altitude.md`);
   - for each child Story: current parent → new parent, or "orphan → <disposition>";
   - what happens to the **source Epic ticket** after re-parenting (keep as historical anchor
     or close — recommend, let the user decide);
   - the per-Epic markdown files to write next (`docs/plans/<saga>-<epic>-epic.md`), deferred
     to `/we:epic` per Epic (this skill does NOT write them).

### Step E4 — approval (ExitPlanMode), then persist + stop

1. Write `docs/plans/<saga>-saga.md` (incl. the `## Promotion Plan` checklist).
2. Do **not** auto-execute the ticketing re-parenting — bulk, partly irreversible. Print the
   Promotion Plan as the next-actions checklist and let the user run it.
3. Output: *"Saga `<saga>` promoted from `<EPIC-KEY>` at `docs/plans/<saga>-saga.md`. Promotion
   Plan ready: create <N> Epics `[<saga>] …`, re-parent <M> Stories. Run `/we:epic
   "<first-epic>"` to formulate the first Epic doc. /we:saga DONE."*

⛔ STOP. No ticketing mutations, no `/we:epic`, no `/we:meet saga` fired inline.

---

## Template

```markdown
---
type: saga-plan
saga: <saga-slug>
vision: <parent-vision-slug>  # optional; omit for orphan Sagas
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: draft | active | landed | abandoned
---

# Saga: <Name>

## The Bet

[One sentence. The multi-bet thing we point energy at.]

## Why Now

[2-4 sentences. What in the Vision, in the market, or in the codebase makes this the right next bet. Anchor to the PRD if there is one.]

## Success Criteria

- [Concrete, externally verifiable.]
- [If the list is long, the Saga is probably two Sagas — soft-warn during Refine.]

## In Scope

- [What this Saga covers.]

## Out of Scope

- [What this Saga does NOT cover. If empty, the Saga isn't bounded — fix that before saving.]

## What Success Eliminates

[Plain prose. "If this lands, we no longer need to argue about X." If you cannot finish this sentence, the Saga isn't a bet yet.]

## Sub-Epics

<!-- mirror:start (auto-generated; do not edit by hand — run /we:saga to refresh) -->

_Mirror of child Epics in the ticketing tool, refreshed YYYY-MM-DD._

| Key | Title | Status | Last activity | Notes |
|---|---|---|---|---|

<!-- mirror:end -->

## Open Questions

- [Things genuinely unsettled. Will be resolved during `/we:meet saga` or as Epics start.]

## Updates Log

- YYYY-MM-DD — created
- YYYY-MM-DD — mirror refresh (N child epics; +a added, −b removed, !c status-changed)

## Notes

[Free-form: links to relevant ADRs, prior decisions, market context.]
```

---

## Hand-off

After Refine or Create: **`/we:meet saga`** (Council validates the Saga against the Vision and
decomposes into Epics with rough sequencing), then **`/we:epic "<epic-name>"`** per Epic. Saga
Solo never decomposes — decomposition benefits from multi-voice tension (PO + Architect + a
rotating domain voice).

---

## Saga-specific rules

(Shared rules live in `po-altitude.md` — these are additional:)

- ALWAYS name what is explicitly **out** of scope during Refine — a Saga without OUT is a Vision.
- ALWAYS use the Jira-grouping convention `[<saga-slug>] <Epic Title>` for the child Epics a
  Promote (or any decomposition) creates.
- ⛔ NEVER create a ticketing-tool item for the Saga itself — Sagas are Markdown-only; only the
  child Epics live in ticketing.
- ⛔ NEVER auto-execute ticketing re-parenting during Promote — produce the checklist, the user
  runs it (bulk, partly irreversible).
