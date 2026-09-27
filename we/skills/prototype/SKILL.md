---
name: prototype
description: >
  A throwaway prototype answering exactly one design question — a terminal shell over a pure
  module, or three UI variants. Triggers: "/we:prototype", "prototype this", "what should this
  look like".
---

# /we:prototype

Throwaway code that answers one question before it gets planned; a story cut around a validated
decision is smaller than one cut around a guess. Write the question at the top of the file first.
The question picks the branch. If it is ambiguous and the user is away, pick the branch that
matches the surrounding code (a backend module → logic, a page → UI) and state that assumption at
the top of the file.

## Both branches

- Next to the module or page it serves, named so a reader sees it is a prototype, inside the
  project's existing routing and tooling.
- One run command, wired into the project's task runner (none → the command at the top of the file).
- State in memory. A database only when persistence is the question, then a scratch store named
  `PROTOTYPE — wipe me`.
- No tests, no error handling beyond running, no abstractions.
- Render the full relevant state after every action or variant switch.

## Logic: "does this state model feel right?"

The logic sits in a pure module (a reducer, a state machine, pure functions over a plain type, or a
class that owns state, whichever fits the question), with no I/O. A disposable terminal shell imports
it and redraws one frame per action: the state pretty-printed, then the keys (`[a] add  [q] quit`).
The frame replaces the previous one instead of scrolling. The module may be lifted into real code;
the shell never is.

## UI: "what should this look like?"

Three variants by default, five at most, that disagree about structure (layout, hierarchy, primary
affordance), not colour. Default: on the existing page behind `?variant=`, data fetching above the
switcher; a new throwaway route only when no page could host it. Variants share leaf components at
most, never a layout, and call stubs instead of real mutations. A floating bar (prev · label · next,
`←`/`→` when no input has focus) updates the URL param through the router and is hidden in
production builds by the project's env check.

## Done

Keep only the answer: in the story plan or ticket the prototype de-risked, an ADR (`/we:grill`
decides whether one is warranted), or the commit message. A snippet that encodes the decision may go
into the ticket. Then delete the prototype; a winning UI variant is rewritten properly, not promoted.

*Adapted from [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT).*
