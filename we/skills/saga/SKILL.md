---
name: saga
description: >
  Saga (Solo) at the Theme altitude: status, refine/create, or promote an overgrown Epic.
  Triggers: "/we:saga", "saga", "theme", "promote".
---

# /we:saga — Saga (Solo) at the Theme altitude

You hold one Saga at `docs/plans/<saga>-saga.md`: a bet inside the Vision with a nameable end. Status is the read-only default.
A Saga is Markdown only; its child Epics may live in ticketing, titled `[<saga-slug>] <Epic Title>`.
Saga Solo never decomposes: Epics come from `/we:meet saga`, each Epic is formulated by `/we:epic`.
Wanted stops: one interview question at a time, and the approval. After the approval you commit, print the next verb and stop.

Shared contract (target and mode, Status, mirror block, drafting, writer, commit path):
`${CLAUDE_PLUGIN_ROOT}/references/apo-hierarchy.md`. Template: `${CLAUDE_PLUGIN_ROOT}/skills/saga/references/template.md`.

| Binding | Saga value |
|---|---|
| Parent | the PRD `docs/plans/<vision>/PRD.md`; without it, `vision: null` and say the Saga is an orphan |
| Children | Epics: ticketing Epics titled `[<saga>] …`, else `docs/plans/*-epic.md` with `saga: <saga>` |
| Active statuses | `draft`, `active` |
| Meet verb | `/we:meet saga` |
| Extra mode | **Promote**: "promote", "re-cut", "this Epic is a Saga", or an Epic key with Story children |

## Frame — four questions, in order

1. **The bet.** One sentence: what we point energy at.
2. **Success criteria.** Externally verifiable; a long list means two Sagas.
3. **Bounded scope.** In and out. A Saga without an out list is a Vision.
4. **What success eliminates.** "If this lands, we no longer argue about ___." Nothing eliminated means
   the Saga does not bite yet.

Soft warning "this reads like a Vision — step up to `/we:vision`, or split into two Sagas?" when the bet
has no end state, the criteria keep growing, the sentence in 4 cannot be finished, or more than ~8
child Epics ran for months without a landing.

## Status, Refine, Create, Mirror-refresh

As in `apo-hierarchy.md` § Target and mode and § Drafting, with the frame above. Create without a PRD:
ask once whether to run `/we:vision` first or proceed as an orphan, and wait. After approval: set
`updated:`, append an Updates Log line, commit, then output and stop:

```text
Saga: docs/plans/<saga>-saga.md (<sha> on <branch>).
Next: /we:meet saga — validate against the Vision and derive the Epics.
```

## Promote — an overgrown ticketing Epic becomes a Saga

For an Epic that holds many Stories, runs for months without a landing and covers several themes.
Ticketing tools have no Saga level, so this is how a Brownfield Epic gets one.

1. **Load and check.** Fetch the Epic and all its child Stories (key, title, status). Weak signal (few
   children, one theme): say so and ask whether it is only a large Epic.
2. **Propose the cut in conversation.** Cluster the Stories into 3–6 candidate Epics by seam, each with a
   slug starting with the Saga slug and a one-line reason. Show the maturity gradient per candidate
   (Done / Active / not started): a lumpy gradient suggests an arbitrary cut. Name every orphan Story
   that fits no candidate; never absorb one silently. Draft only after the Saga slug, the Epic set and
   the orphan disposition are agreed.
3. **Draft** per § Drafting: the Saga doc, distilled from the source Epic's doc when one exists (that
   doc stays as a reference), plus a `## Promotion Plan` checklist: the N ticketing Epics to create
   (`[<saga>] <Title>`), each Story's old and new parent or its orphan disposition, what happens to the
   source Epic ticket (keep as anchor or close: recommend, the user decides), and the Epic docs that
   `/we:epic` writes next.
4. **After approval:** commit the Saga doc. Run the ticketing half only on the user's explicit go naming
   the counts ("create 4 Epics, re-parent 23 Stories"); it is bulk and partly irreversible. Without that
   go the checklist stays in the doc for the user. Output, then stop:

   ```text
   Saga <saga> promoted from <EPIC-KEY>: docs/plans/<saga>-saga.md (<sha>). Promotion Plan: <N> Epics, <M> Stories — <executed | open for you>.
   Next: /we:epic "<first-epic>"
   ```
