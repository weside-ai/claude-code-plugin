---
name: epic
description: >
  Epic plan: one outcome serving a goal-file metric — status from plan + ticketing mirror, or refine/create.
  Triggers: "/we:epic", "epic", "refine epic", "new epic".
---

# /we:epic — one epic plan

You hold one Epic at `docs/plans/<epic>-epic.md`: one outcome that carries `serves: <metric>` of the goal file and ships a coherent change (L0 §Units). Status is the read-only default.
The plan is the durable artifact; a ticketing Epic, where one exists, is its index. `/we:epic` owns the Stories mirror.
`/we:epic` never writes a Story plan: Stories come from the Sequencing section, and each plan comes from a refiner worker the epic's master starts (`/we:plan-story`), never from the epic owner (L0 §Lifecycle).
Wanted stops: one interview question at a time, and the approval. After the approval you run the ticket step, commit, print the next verb and stop.

Shared contract (target and mode, Status, mirror block, drafting, writer, commit path, `## Success Criteria`):
`${CLAUDE_PLUGIN_ROOT}/references/epic-plan.md`. Template: `${CLAUDE_PLUGIN_ROOT}/skills/epic/references/template.md`.
Tickets: `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`.

| Binding | Epic value |
|---|---|
| Parent | `serves: <metric>` of the goal file; without one, `serves: null` and say the Epic serves no metric yet (no user and metric → no work, L0 §Units) |
| Children | Stories: ticketing children of the Epic ticket, else `docs/plans/*-story.md` whose `epic:` matches |
| Active statuses | `draft`, `selected`, `in-progress` |

## Frame

- **Why this slice now?** Which goal-file metric it moves and why it is next.
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
| More than one outcome, more Stories than the epic limit, longer than ~2 weeks | "This is two outcomes — cut it into linked epics serving the same metric?" |
| One user-visible change, one obvious AC set | "This is Story-sized — one Story in an existing epic?" |
| Two unrelated architecture seams | "This Epic does two things — split or trim?" |

An Epic that gains a Story is doing its job; one that doubles mid-flight is a scope failure: soft-warn.

## Status extras

On top of `epic-plan.md` § Target and mode step 3: the Refined bucket; the drift line
`⚠ <N> Stories Active in ticketing without a refined plan`; the size check above, rendered only when it
fires, because Status is the path people rerun; and the offer `[s]` print `/we:master <epic>` for
the master that pulls the recommended next Story.

## Create extras

- No goal-file metric found: ask once which metric the Epic serves, or proceed with `serves: null`, and wait.
- **From a Story ticket** (`/we:epic {STORY-KEY}` for a too-big story; the key
  resolves to Create per `epic-plan.md` § Target and mode): the ticket's newest comment carries the slice cut, the sequencing and the rejected alternative. That
  comment is the interview's starting point; the rough Stories come from it.
- Ticket step after approval, when ticketing is detected: create exactly one ticketing Epic, titled
  `<Title>`, description = one-line purpose + plan path; set `ticket:`. A source
  Story ticket is re-parented under the new Epic or closed as the user chose in the approval. The
  approval message names this step (`epic-plan.md` § Drafting step 4); unnamed, it does not run. Never
  create Story tickets here: the refiner's plan run creates each one (owner 25.09.2026, no unasked tickets).
- Refine with an existing ticketing Epic: update its description to the pointer form when it holds
  more.

## After approval — output

Before the commit, check the epic's claims: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check-plan-identifiers.py
<epic plan> --ref origin/<default>`, every command the epic names against the tool's `--help` (the flag
exists, the id form matches), and every claim about a repo rule (risk paths, CI, a gate) as `file:line` on
`origin/<default>`. A false claim is fixed here, before the first story's refiner copies it (a
`-k` the command lacks and a risk-paths rule that does not exist reached the story plan).

Set `updated:`, append an Updates Log line, run the ticket step, commit, then output and stop:

```text
Epic: docs/plans/<epic>-epic.md (<sha> on <branch>). Ticket: <KEY | none>.
Next: <see below>
```

- Stories in the mirror or in `## Sequencing` → `/we:master <epic>`: the epic's master pulls each
  Story, starts a refiner worker for one without a plan, and builds each Story as its own PR (L0 §Units).
- No Stories yet → `/we:council` when the cut is contentious or seams compete; otherwise sketch the
  Stories in a Refine.
