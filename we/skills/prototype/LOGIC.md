---
name: prototype-logic
description: Logic-branch reference for /we:prototype — pure module behind a disposable terminal shell
type: reference
---

# Logic Prototype

A tiny interactive terminal app that lets the user drive a state model by hand. The right
shape when the question is about **business logic, state transitions, or data shape** — the
kind of thing that looks reasonable on paper but only feels wrong once you push it through
real cases.

If the question is "what should this look like" — wrong branch, use [UI.md](UI.md).

## Process

### 1. State the question

Before writing code, write down what state model and what question you're prototyping — one
paragraph, at the top of the file. A logic prototype that answers the wrong question is pure
waste; making the question explicit lets it be checked later, whether the user is watching
now or returning to it AFK.

### 2. Isolate the logic in a portable module

Put the actual logic — the bit answering the question — behind a small, pure seam that could
be lifted into the real codebase later. The terminal shell around it is throwaway; the logic
module isn't. Pick the shape that fits the question, not the one easiest to wire up:

- **A pure reducer** — `(state, action) => state`, when actions are discrete events.
- **A state machine** — explicit states and transitions, when "which actions are even legal
  right now" is part of the question.
- **A set of pure functions** over a plain data type, when there's no implicit current state.
- **A class with a clear method surface**, when the logic genuinely owns ongoing state.

Keep it pure: no I/O, no terminal code inside the module. The shell imports it and calls in;
nothing flows the other direction.

### 3. Build the smallest shell that exposes the state

On every action: clear the screen and re-render one stable frame (current state
pretty-printed, then the keyboard shortcuts at the bottom — `[a] add  [t] tick  [q] quit`).
Replace the frame, don't append — the user should see one view, not growing scrollback.
Use the host project's language and runtime; if the project has no obvious runtime, ask.

### 4. Wire one run command

Add a script to the project's existing task runner. No task runner → put the command at the
top of the file.

### 5. Hand it over and capture the answer

Give the user the run command; they drive it. The interesting moments are "wait, that
shouldn't be possible" — bugs in the *idea*, which is the whole point. When it's done its
job, capture the answer (see SKILL.md "When done") and delete the shell; lift the validated
logic module into the real code if it earned it.

## Anti-patterns (each paired with the fix)

- **Don't blur logic and shell — keep the module pure** so it stays portable past the
  prototype's lifetime.
- **Don't wire it to the real database — use an in-memory store**, unless the question IS
  persistence.
- **Don't generalise ("what if we later want X") — the prototype answers one question.**
- **Don't ship the shell — the logic module is the part worth keeping.**
