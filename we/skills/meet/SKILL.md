---
name: meet
description: >
  Council meeting at one APO altitude — validates the artifact, decomposes it, hands off to the
  Solo skill. Triggers: "/we:meet", "vision meeting", "epic meeting", "run a meeting".
---

# /we:meet — a Council meeting at one altitude

You run one meeting: load the item, convene `/we:council` if the user wants it, and decompose the item into the next altitude down.
A meeting writes no file, creates no ticket and writes no code. It ends with the synthesis, the decomposition and the next verb printed.
The Solo verb at the same altitude folds the result into the doc; the Solo verb one altitude down formulates each child.
Wanted stops: the council offer, the prioritisation with the user, the end. Every other status note goes with the next tool call.

Altitudes, rosters and the synthesis headings: `${CLAUDE_PLUGIN_ROOT}/references/apo-hierarchy.md`.

```text
/we:meet vision|saga|epic|story [target] [--council | --no-council | --council=role,role]
```

No type given: list the four and ask which one.

## How every meeting runs

1. **Load** the target and its parent doc per the type below. Read the instruction files and ADRs the
   topic touches before framing: a council framed on a wrong assumption argues about the wrong thing.
2. **Council.** `--council` convenes, `--no-council` runs solo, `--council=…` convenes with that roster.
   No flag: ask "Convene the council for this <type> meeting?" as a plain offer; never guess from
   complexity. Convene with `Skill(skill: "we:council", args: "\"<framing question>\" --meeting=<type>")`,
   or `--council=<roles>` in place of `--meeting` for an explicit roster. It takes a few minutes.
   A council that aborts on its preflight leaves the meeting solo: say which lenses are missing.
3. **Decompose** with the user, using the synthesis's Agreement and Tension. Name dependencies and the
   first child to formulate.
4. **Close** with one message: the synthesis's `## Recommendation`, the child table (name, one-line
   purpose, acceptance shape or success signal, order, dependencies), the decisions the user made, and
   the hand-off below. Run the Solo verb in the same session: its brief carries the synthesis and the
   table verbatim.

## vision → Sagas

Frame: "Why does this product exist, and who is it for? Which Sagas does that imply?" Load the PRD
`docs/plans/<vision>/PRD.md`. The council pressure-tests the bets: is the audience real, is the change
ambitious enough, what are we ignoring. Derive 3–5 candidate Sagas; the user marks which are active.
Hand-off: `/we:vision` to fold the Saga bets into the PRD, then `/we:saga "<name>"` per Saga.

## saga → Epics

Frame: "Does this Saga serve the PRD, and which 3–6 Epics deliver the bet, in what order?" Load
`docs/plans/<saga>-saga.md` and the PRD. Each Epic is finishable and coherent, its slug starts with the
Saga slug. Hand-off: `/we:saga <saga> refine` to fold the Epic set in, then `/we:epic "<name>"` per Epic.

## epic → Stories

Frame: "What is the smallest version that delivers the win, and which Stories build it?" Load
`docs/plans/<epic>-epic.md` (or the ticketing Epic) and its Saga. Worth it when the scope is
contentious, seams compete or the order is unclear; for a well-formulated Epic with sketched Stories,
go straight to `/we:story` instead. Each Story is a tracer bullet: end to end through every layer, one at
a time, never one layer per Story. Before locking the cut, check for an enabling change that makes
several Stories easy; it becomes the first Story. The meeting produces names and acceptance shape, never
a build-ready plan. Hand-off: `/we:epic <epic> refine` to fold the cut into `## Sequencing`, then
`/we:story "<name>"` per Story.

## story → a build-ready plan

Frame: "Is the scope clear, and which of the defensible implementations do we take?" Load the ticket
with its comments, or the topic. For a contentious Story: unclear ACs, a 50/50 implementation choice,
repeated bounce-backs from Build. Settle in, out and the shape with the user. Hand-off:
`/we:story <ticket-or-topic>`, which runs the interview with the synthesis as input and writes the plan.
