---
name: meet
description: >
  Run a structured meeting — vision, initiative, or refinement. Each meeting
  is a facilitated workflow at its level (Saga / Epic / Story) and may convene
  a council of companions. refinement hands off to /we:refine. Use when the
  user says "/we:meet", "vision meeting", "initiative meeting", "refinement
  meeting", "let's meet", "run a meeting".
---

# /we:meet

**Purpose:** Run one of three structured meetings, each at its own altitude:

| Meeting | Level | Input | Output |
|---|---|---|---|
| `vision` | Saga / year | Company vision, market, long-term goals | Saga definitions, priorities |
| `initiative` | Epic / quarter | A Saga | Saga → Epic decomposition, sequencing |
| `refinement` | Story / cadence | An Epic or a concrete item | Clarified scope → hands off to `/we:refine` |

A meeting is a *facilitated workflow*; the **council** (`/we:council`) is the deliberation engine a meeting can convene. The meeting produces consensus; the activity skill (`/we:refine`, `/we:story`) produces the artifact.

## Invocation

```
/we:meet vision [topic]
/we:meet initiative [saga]
/we:meet refinement [ticket-or-topic]
        [--council | --no-council]
```

If no meeting type is given, list the three and ask which one.

## How every meeting runs

1. **Resolve the meeting type** from the first argument.
2. **Council decision** — unless a flag forces it:
   - `--council` → convene it. `--no-council` → run solo.
   - Neither flag → **offer it**: *"Convene the council for this {type} meeting? [y/n]"*. No "complexity" guessing — always a plain offer.
   - If convened → invoke the council via `Skill(skill="council", args="\"<framing question>\" --meeting=<type>")` — the topic and the `--meeting` flag are passed in the `args` string; the council skill parses them. (Unlike `/we:refine`, the council skill is light — its own sub-agents do the heavy work — so invoking it inline is fine.) The roster for the type comes from `.weside/config.json` `council.meetings.<type>` (or the shipped default). Feed the synthesis into the meeting workflow below.
3. **Run the meeting workflow** for the type.
4. **Close out** — vision and initiative produce a written summary artifact (the final step of each workflow below) and offer to persist it; refinement instead hands off to `/we:refine` per its workflow. The Agentic-PO convention for persisted artifacts is `docs/plans/<saga>/`.

## Meeting: vision

**Frame:** "Where do we want to be in ~12 months? Which continents do we work on?"

1. Establish the inputs — current vision, market situation, long-term goals. Ask for what is missing.
2. (Council) — convene if chosen; the council weighs candidate directions from each lens.
3. Identify candidate **Sagas** — coherent multi-quarter bodies of work.
4. Prioritise them with the user; mark which are active this year.
5. Artifact: a vision summary — the Sagas, the priorities, the reasoning.

## Meeting: initiative

**Frame:** "How does this Saga break into Epics, in what order?"

1. Load the Saga (from its plan folder or from the user).
2. (Council) — convene if chosen; the council stress-tests the decomposition.
3. Decompose the Saga into **Epics** — each a coherent, finishable body of work.
4. Sequence the Epics; name dependencies.
5. Artifact: an initiative summary — the Epic set, sequencing, dependencies, open questions.

## Meeting: refinement

**Frame:** "What is the next concrete story, and what is its scope?"

1. Load the Epic or concrete item (a ticket key, or a topic).
2. (Council) — convene if chosen; the council pressure-tests scope and acceptance.
3. Consolidate the scope with the user — what is in, what is out, the shape of the story.
4. **Hand off to `/we:refine`:** print the instruction *"Scope is clear — now run `/we:refine <ticket-or-topic>` to produce the plan."*
   Do **not** call `Skill(skill="refine")` — `/we:refine` is a large interactive skill; invoking it inline inflates context. The hand-off is an explicit instruction to the user.

## Rules

- **Always offer the council** (unless a flag decides) — never infer "complexity".
- **refinement hands off by instruction**, not by `Skill()` call.
- **Degrade gracefully** — no council configured, no weside: the council falls back to generic agents (handled by `/we:council`), or the meeting runs solo.
- A meeting produces **consensus + a summary**, not code. Implementation is `/we:story`.

## References

- `we/skills/council/SKILL.md` — the deliberation engine a meeting convenes
- `we/skills/refine/SKILL.md` — what a refinement meeting hands off to
- `we/skills/CLAUDE.md` — Tätigkeit-vs-Meeting design rationale
- Source: the Agentic Product Ownership framework design notes, § 1.3.2 (Meetings)
