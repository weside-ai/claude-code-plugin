---
name: prototype
description: >
  Build a throwaway prototype that answers exactly one design question before it gets
  planned — a logic/state question (interactive terminal shell over a pure module) or a
  UI question (3 radically different variants behind ?variant=). Use when the user says
  "/we:prototype", "prototype this", "does this state model feel right",
  "what should this look like".
---

# Prototype

A prototype is **throwaway code that answers a question**. The question decides the shape.
Answer the question *before* it gets planned — a `/we:story` cut around a validated decision
is smaller and safer than one cut around a guess.

## Pick a branch

Identify which question is being answered — from the user's prompt, the surrounding code, or
by asking if the user is around:

- **"Does this logic / state model feel right?"** → [LOGIC.md](LOGIC.md). A tiny interactive
  terminal app that pushes the state model through cases that are hard to reason about on
  paper.
- **"What should this look like?"** → [UI.md](UI.md). Several radically different UI
  variants on a single route, switchable via a `?variant=` URL param and a floating bar.

The two branches produce very different artifacts — getting this wrong wastes the whole
prototype. If the question is genuinely ambiguous and the user isn't reachable, default to
whichever branch matches the surrounding code (a backend module → logic; a page or
component → UI) and state the assumption at the top of the prototype.

## Rules that apply to both branches

1. **Throwaway from day one, and clearly marked.** Locate the prototype next to the module
   or page it's prototyping for, named so a casual reader sees it's a prototype. Follow the
   project's existing routing/tooling conventions — don't invent new top-level structure.
2. **One command to run.** Wire it into the project's existing task runner. The user starts
   it without thinking.
3. **No persistence by default.** State lives in memory — persistence is usually the thing
   being *checked*, not a dependency. If the question explicitly involves a database, hit a
   scratch store with a clear "PROTOTYPE — wipe me" name.
4. **Skip the polish — a prototype that needs tests is no longer a prototype.** No tests,
   no error handling beyond runnability, no abstractions. Learn fast, then delete.
5. **Surface the state.** After every action (logic) or on every variant switch (UI), render
   the full relevant state so the user sees what changed.
6. **Delete or absorb when done.** Fold the validated decision into the real code or plan,
   then remove the prototype — don't leave it rotting in the repo.

## When done

The **answer** is the only thing worth keeping. Capture it durably — in the Story plan or
ticket the prototype was de-risking, an ADR (via `/we:grill`'s 3-gate), a commit message, or
a `NOTES.md` next to the prototype if running AFK. A prototype snippet that encodes the
decision may go into the ticket verbatim — the one exception to the no-code-in-tickets rule
(`references/ticket-briefs.md`).

---

*Adapted from [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT).*
