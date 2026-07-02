---
name: epic
description: >
  Epic (Solo) — PO skill at the Initiative altitude. Default Status mode
  renders snapshot + drift + next move from the Epic plan and ticketing
  mirror; Refine/Create sharpen the doc via plan-mode; Mirror-refresh is
  a light write. Use when the user says "/we:epic", "epic", "initiative",
  "refine epic", "new epic". Decompose into Stories via /we:meet epic.
---

# Epic (Solo) — Product Owner at the Initiative altitude

You hold the Epic at the Initiative altitude — a bounded deliverable that serves a Saga and ships a chunk of working product. This skill is the Solo half; the Council half is `/we:meet epic`. The two interleave: a Council to decompose or to re-cut, then Solo to sharpen the Epic doc itself.

> **APO altitude:** Epic (Solo). Upstream: `/we:meet saga` decomposes a Saga into Epics that land here. Downstream: `/we:meet epic` decomposes this Epic into Stories; `/we:story "<ticket-or-topic>"` writes each build-ready plan. See [`docs/concepts/meetings.md`](../../../docs/concepts/meetings.md) for the four-altitude map.
>
> **Artifact:** the Epic plan at `docs/plans/<saga>-<epic>-epic.md`. Optionally also a ticketing-tool Epic (e.g. a Jira Epic) with the same name. Both work; pick per Epic. The Markdown plan is always the durable artifact; the ticket, where one exists, is an index. The skill *mirrors* the child Stories from the ticketing tool into a clearly-marked block inside `CONCEPT.md`; that mirror is convenience, not state.
>
> **Epic vs. Saga vs. Story:** Epics finish; categories don't. If the "Epic" reads like a permanent area of work ("Mobile", "Backend", "Voice"), it isn't one. If it has no nameable end at all, it's a Saga in disguise. If it fits in a single Story-shaped change, it's a Story — `/we:story` is the right skill. The skill flags these as soft warnings during Refine, never as hard blocks.

---

## Shared skeleton

**Read `${CLAUDE_PLUGIN_ROOT}/references/po-altitude.md` at boot** — it defines the Smart-Mode
resolution (target + intent), Modes A–D (Status / Refine / Create / Mirror-refresh), the
Jira-grouping convention, the Companion-voice rule, and the shared rules. This file binds the
parameters and carries only what is Epic-specific.

**Parameter binding:**

| Parameter | Epic value |
|---|---|
| The doc | `docs/plans/<saga>-<epic>-epic.md` (CONCEPT) |
| Parent doc | the Saga (`docs/plans/<saga>-saga.md`) — without it, flag the Epic as Saga-less |
| Children | child **Stories** from the ticketing tool (via "Epic Link" / "Parent") |
| No-ticketing fallback | scan `docs/plans/{KEY}-story.md` frontmatter (Context references this Epic) |
| Active statuses (target resolution) | `draft \| in-progress \| selected` |
| Meet command | `/we:meet epic` |
| Downstream | `/we:story <KEY>` per Story |

---

## Prerequisites

- `.weside/` configured (run `/we:setup` once per project if missing — does not block this skill).
- Ticketing tool detected per `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`; none → filesystem fallback above, tell the user.
- Parent Saga loaded if it exists.

---

## Epic-specific pieces

### Status (Mode A) extras

- Per child Story, also capture whether a refined plan exists at `docs/plans/{KEY}-story.md`
  (legacy fallback `{KEY}-plan.md`) and render a **Refined** bucket (plan ready, not started)
  plus a drift line `⚠ <N> sub-stories marked Active in ticketing without a refined plan`.
- **Size check (Saga-in-disguise)** — render only when it fires: child Stories > ~10 AND active
  for months with no single landing →

  ```text
  ⚠ <N> child Stories (> ~10) and active for <months> with no single landing —
    this Epic is reading like a Saga. Consider `/we:saga promote <KEY>` to re-cut it.
  ```

  It lives in Status (not only Refine) because Status is the 90%-path — nobody re-runs Refine
  on a healthy-looking Epic. Soft nudge, never a hard block.
- Footer extras: `[s]` hand off to `/we:story <KEY>` (the recommended next Story — print the
  command, never invoke inline); `[p]` promote to a Saga via `/we:saga promote <KEY>` (only
  offered when the Size check fired; print, never invoke).

### The Epic frame (Refine Step B1 / Create walk)

- **Why this slice now?** What part of the Saga does this Epic deliver, and why is it next?
- **What user journeys are touched?** Which users feel the change when this Epic ships?
- **Target architecture seam.** The new primitive, the migration shape — not the implementation, the SHAPE.
- **Dependencies.** Other Epics, infra, external services, open decisions.
- **Risk-driven sequencing.** What de-risks the slice early? What can be cut if the slice runs long?
- **What are the rough Stories?** First-cut breakdown — names with acceptance shape; detail comes from `/we:meet epic`.
- **When is it DONE?** The success metric — what shipped, what a user can newly do, what telemetry confirms it.
- **Scope-drift + boundary checks** — see the table below.

Sizing is by *bet shape* (does it have an end, does it ship a coherent user-visible change),
not by time window — the legacy "quarter-sized" assertion is deliberately gone.

### Create (Mode C) extras

- If no Saga exists, ask: *"No Saga document found. Run `/we:saga \"<saga-name>\"` first, or
  proceed Saga-less and flag it in the Epic?"* Default suggestion: run the Saga first. Wait.
- If stories were already sketched in the conversation, create them as ticketing shells now so
  they appear in the Mirror table — this lets the hand-off skip `/we:meet epic`.
- Default to creating the ticketing-tool Epic alongside the Markdown when a tool is detected;
  Markdown-only is a fine first cut. When creating the ticket: carry the Epic name, the
  one-paragraph Vision section, and a pointer to the CONCEPT path — never the full template.

### Epic boundaries (soft warnings, not hard blocks)

| Signal | Soft warning |
|---|---|
| Reads like a permanent area of work ("Mobile", "Backend", "Voice") | *"That's an area, not an initiative. Want to formulate the specific change as a smaller Epic or a Story?"* |
| Child-Story set growing past ~10 with no landings, active for many months | *"This is starting to read like a Saga. Want to step up to `/we:saga`, or split into two Epics?"* |
| Scope is one user-visible change, one obvious AC set | *"This is Story-sized. Want to drop down to `/we:story`?"* |
| Multiple unrelated architecture seams in scope | *"This Epic is doing two things. Split into two Epics, or trim one?"* |

The user decides. The skill does not block.

### Epic status (lifecycle)

`status:` frontmatter of the Epic itself: **In Progress** (actively shipping) · **Selected**
(refined, next up) · **Backlog** (formulated, paused) · **Done** (all Stories shipped, no
further scope). Stories emerge during work — an Epic that gains a Story is doing its job; an
Epic that *doubles* mid-flight is a scope failure — soft-warn, suggest a re-cut or split.

### Mirror block

Format, markers, buckets, refresh rules: `${CLAUDE_PLUGIN_ROOT}/references/mirror-block.md`.
The epic table carries the **Plan** column (`✓` if `docs/plans/<KEY>-story.md` exists — the
refined-vs-not signal).

---

## Template

```markdown
---
type: epic-plan
epic: <epic-slug>
saga: <parent-saga-slug>
ticket: <TICKETING-KEY-if-any>
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: draft | in-progress | selected | backlog | done
---

# Epic: <Epic Name>

## Vision

[Why does this Epic exist? What part of the parent Saga does it deliver?
Who feels the change when it ships? 3-6 sentences, narrative voice. The
decomposition meeting reads this FIRST.]

## Scope

**IN:**
- [Concrete deliverable 1]
- [Concrete deliverable 2]

**OUT:**
- [Explicitly excluded — the easiest cut if the slice runs long]
- [Adjacent work that belongs to a different Epic]

## Target architecture

[The seam, the new primitive, the migration shape. Not the implementation —
the SHAPE the implementation will take. Reference existing ADRs and
primitives where relevant.]

## Sequencing

[Risk-driven order. What de-risks the slice early? What depends on what?
What can be cut if the slice runs long? Name the first Story to refine.]

## Dependencies

- [Other Epic, infra, external service, open decision]

## Stories

<!-- mirror:start (auto-generated; do not edit by hand — run /we:epic to refresh) -->

_Mirror of child Stories in the ticketing tool, refreshed YYYY-MM-DD._

| Key | Title | Status | Plan | Last activity | Notes |
|---|---|---|---|---|---|

<!-- mirror:end -->

## Success Metrics

[When is this Epic DONE? What shipped, what a user can do that they
couldn't before, what telemetry confirms "this worked". One paragraph.]

## Open Questions

- [Things the Solo session could not resolve — fodder for `/we:meet epic`]

## Updates Log

- YYYY-MM-DD — created
- YYYY-MM-DD — mirror refresh (N child stories; +a added, −b removed, !c status-changed)

## Notes

[Free-form: links to relevant ADRs, prior decisions, design context.]
```

---

## Hand-off

After Refine or Create, the path depends on whether the Stories table already has entries:

- **Stories already in the Mirror table** → go directly to **`/we:story <KEY>`** per Story.
  Skip `/we:meet epic` unless the decomposition feels contentious or sequencing is unclear.
- **Stories table is empty** → either run **`/we:meet epic`** (the Council validates the slice
  and decomposes into Story shapes — worth it when the Epic is new, contentious, or seams
  compete), or sketch stories yourself, Refine again, then go straight to `/we:story`.

`/we:meet epic` is not mandatory — it adds value for contentious decomposition, it is overhead
for a well-formulated Epic. Either way, each Story still needs its own `/we:story <KEY>` run;
Epic Solo never decomposes inline.

---

## Epic-specific rules

(Shared rules live in `po-altitude.md` — these are additional:)

- ALWAYS write a narrative Vision section during Refine — the decomposition meeting reads it FIRST.
- ALWAYS name explicit OUT-of-scope items — the easiest cut if the slice runs long.
- ⛔ NEVER write a full `/we:story` plan inside an Epic session — Stories are downstream, hand off.
- ⛔ NEVER treat a permanent area of work as an Epic — soft-warn and suggest reframing.
