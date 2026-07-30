---
description: When a story needs /loop or /goal, which to pick and why /goal is the expensive exception, and what a plan must carry before unattended work is legitimate. Loaded by /we:story, /we:orchestrate.
---

# Long-running work: `/loop` and `/goal`

Consumers: `/we:story` (emits the invocation into the plan), `/we:orchestrate`
(runs waves under it). Programme mechanics — the state file, living plans,
rollback — stay in [`programme-discipline.md`](programme-discipline.md).

## Pick by cost, not by taste

| | `/loop` | `/goal` |
|---|---|---|
| Next round starts | on a delay (fixed, or self-paced dynamic) | after every turn |
| Exit | model judgement (`ScheduleWakeup(stop: true)`) | a **small model evaluates your condition** after every turn |
| Cost | one wakeup per round | **an evaluator call per turn** |

**`/loop` is the default. `/goal` is the exception.**

`/goal`'s evaluator fires after *every* turn, including the twenty in a row where
the condition obviously cannot have changed yet. Over a long build that is a
steady drip of calls for an answer nobody needed. Reach for it only when being
wrong about "am I done" is expensive:

- a money, auth or tenant-isolation path,
- a migration or a cutover with a hard finish line,
- unattended work where nobody will read the summary for hours.

Everywhere else, write the exit criterion into the **plan and the state file**
and let the loop judge against it. Same criterion, no per-turn evaluator.

## What a plan owes before unattended work is legitimate

`/loop` only works when four things are true. If they are not, the first round's
job is to make them true:

1. a **state file** carries memory between rounds (the loop has no context),
2. **verification is scriptable** and unattended — see
   [`verification.md`](verification.md); this is the one that is usually missing,
3. the **exit criterion is written down and checkable**, not felt,
4. each round leaves main releasable, so stopping mid-programme is safe.

Point 2 is why the verification contract and this file arrived together. A loop
that cannot verify is a loop that produces unchecked commits at 3am.

## What `/we:story` emits

At the end of a refinement, when the work spans more than one sitting, print the
ready-to-paste invocation — do not invoke it:

```text
Recommended next: /we:orchestrate PROJ-1234

Long-running:
  /loop <the round's task, verbatim from the plan's exit criterion>
```

Add `/goal` **only** when the story meets the critical bar above, and say why in
one clause:

```text
  /goal <machine-checkable condition>     ← money path; wrong-about-done is expensive
```

An exit criterion is checkable when someone else could run it. "Rooms wave is
finished" is not; "all six W3 stories merged and the parity boxes for §1–§5
ticked" is.
