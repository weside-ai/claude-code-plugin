---
name: epic
description: >
  Epic (Solo) at the Initiative altitude: status from plan + ticketing mirror, or refine/create.
  Triggers: "/we:epic", "epic", "refine epic", "new epic".
---

# /we:epic — Epic (Solo) at the Initiative altitude

You hold one Epic at `docs/plans/<epic>-epic.md`: a bounded deliverable that serves a Saga and ships a coherent change. Status is the read-only default.
The plan is the durable artifact; a ticketing Epic, where one exists, is its index. `/we:epic` owns the Stories mirror.
Epic Solo never decomposes and never writes a Story plan: Stories come from `/we:meet epic` or the Sequencing section, each plan from `/we:story`.
Wanted stops: one interview question at a time, and the approval. After the approval you run the ticket step, commit, print the next verb and stop.

Shared contract (target and mode, Status, mirror block, drafting, writer, commit path, `## Success Criteria`):
`${CLAUDE_PLUGIN_ROOT}/references/apo-hierarchy.md`. Template: `${CLAUDE_PLUGIN_ROOT}/skills/epic/references/template.md`.
Tickets: `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`.

| Binding | Epic value |
|---|---|
| Parent | the Saga `docs/plans/<saga>-saga.md`; without it, `saga: null` and say the Epic has no Saga |
| Children | Stories: ticketing children of the Epic ticket, else `docs/plans/*-story.md` whose `epic:` matches |
| Active statuses | `draft`, `selected`, `in-progress` |
| Meet verb | `/we:meet epic` |

## Frame

- **Why this slice now?** Which part of the Saga it delivers and why it is next.
- **Who feels it?** The user journeys the change touches.
- **Target architecture.** The seam, the new primitive, the migration shape; not the implementation.
- **Dependencies.** Other Epics, infrastructure, external services, open decisions.
- **Sequencing by risk.** What de-risks first, what gets cut if the slice runs long, the first Story.
- **Rough Stories.** Names with acceptance shape, each a tracer bullet (end to end through every layer,
  never one layer per Story); an enabling refactor that makes several Stories easy goes first.
- **Success criteria.** What shipped, what a user can newly do, what telemetry confirms it.

| Boundary signal | Soft warning |
|---|---|
| A permanent area ("Mobile", "Voice") | "That is an area, not an initiative — which specific change?" |
| More than ~10 Stories, active for months, no landing | "This reads like a Saga — `/we:saga promote <KEY>`?" |
| One user-visible change, one obvious AC set | "This is Story-sized — `/we:story`?" |
| Two unrelated architecture seams | "This Epic does two things — split or trim?" |

An Epic that gains a Story is doing its job; one that doubles mid-flight is a scope failure: soft-warn.

## Status extras

On top of `apo-hierarchy.md` § Target and mode step 3: the Refined bucket; the drift line
`⚠ <N> Stories Active in ticketing without a refined plan`; the size check above, rendered only when it
fires, because Status is the path people rerun; and the offers `[s]` print `/we:story <KEY>` for the
recommended next Story, `[p]` print `/we:saga promote <KEY>` (only when the size check fired).

## Create extras

- No Saga found: ask once whether to run `/we:saga "<name>"` first or proceed with `saga: null`, and wait.
- **From a Story ticket** (`/we:epic {STORY-KEY}`, printed by `/we:story` for a too-big story; the key
  resolves to Create per `apo-hierarchy.md` § Target and mode): the ticket's newest comment carries the slice cut, the sequencing and the rejected alternative. That
  comment is the interview's starting point; the rough Stories come from it.
- Ticket step after approval, when ticketing is detected: create exactly one ticketing Epic, titled
  `[<saga>] <Title>` under a Saga, description = one-line purpose + plan path; set `ticket:`. A source
  Story ticket is re-parented under the new Epic or closed as the user chose in the approval. The
  approval message names this step (`apo-hierarchy.md` § Drafting step 4); unnamed, it does not run. Never
  create Story tickets here: `/we:story` creates each one (Foxy 25.09.2026, no unasked tickets).
- Refine with an existing ticketing Epic: update its description to the pointer form when it holds
  more.

## After approval — output

Set `updated:`, append an Updates Log line, run the ticket step, commit, then output and stop:

```text
Epic: docs/plans/<epic>-epic.md (<sha> on <branch>). Ticket: <KEY | none>.
Next: <see below>
```

- Stories in the mirror → `/we:story <KEY>` for the first one; a Story named only in `## Sequencing` →
  `/we:story "<name>"`. `/we:orchestrate <epic>` builds the approved Stories serially onto one PR.
- No Stories yet → `/we:meet epic` when the cut is contentious or seams compete; otherwise sketch the
  Stories in a Refine and go straight to `/we:story`.
