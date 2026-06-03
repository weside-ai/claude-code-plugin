---
name: meet
description: >
  Run a structured Council meeting at one of four APO altitudes — vision,
  saga, epic, or story. Each meeting validates the current artifact and
  decomposes it into the next altitude's items (Vision → Sagas, Saga →
  Epics, Epic → Stories, Story → build-ready). Convenes the council
  (`/we:council`) with a roster tuned to the altitude. Story meetings hand
  off to `/we:story` (Solo); the others hand off to the corresponding
  Solo skill (`/we:vision`, `/we:saga`, `/we:epic`). Use when the user says
  "/we:meet", "vision meeting", "saga meeting", "epic meeting", "story
  meeting", "let's meet", "run a meeting".
---

# /we:meet

**Purpose:** Run one of four structured Council meetings, each at its own APO altitude:

| Meeting             | Altitude | Input              | Output (decomposes into) | Hand-off               |
| ------------------- | -------- | ------------------ | ------------------------ | ---------------------- |
| `vision`            | Vision   | a PRD / vision     | Sagas                    | `/we:vision` (refine PRD), then `/we:saga` per Saga |
| `saga`              | Saga     | a Saga / theme     | Epics                    | `/we:saga` (refine SAGA), then `/we:epic` per Epic |
| `epic`              | Epic     | an Epic / quarter  | Stories                  | `/we:epic` (refine EPIC), then `/we:story` per Story |
| `story`             | Story    | a Story / ticket   | a build-ready plan       | hands off to `/we:story` (Solo) for the plan write |

A meeting is a *facilitated workflow*; the **council** (`/we:council`) is the deliberation engine each meeting convenes. The meeting produces synthesis + decomposition; the activity skills (`/we:vision`, `/we:saga`, `/we:epic`, `/we:story`) produce the artifact at each altitude. The Build pipeline (`/we:build`) is downstream of `/we:story` and is not a meeting type.

For the methodology source of truth, see [`docs/concepts/meetings.md`](../../../docs/concepts/meetings.md) (altitude map, meeting summaries, roster defaults) and [`docs/concepts/companion-framework.md`](../../../docs/concepts/companion-framework.md) (council mechanic + role lenses).

## Invocation

```
/we:meet vision [topic-or-prd]
/we:meet saga   [saga-or-topic]
/we:meet epic   [epic-or-ticket]
/we:meet story  [ticket-or-topic]
        [--council | --no-council]
        [--council=role1,role2,…]   # explicit roster override
```

If no meeting type is given, list the four and ask which one.

## How every meeting runs

1. **Resolve the meeting type** from the first argument (`vision` / `saga` / `epic` / `story`).
2. **Council decision** — unless a flag forces it:
   - `--council` → convene it. `--no-council` → run solo.
   - Neither flag → **offer it**: *"Convene the council for this {type} meeting? [y/n]"*. No "complexity" guessing — always a plain offer.
   - **Env-flag preflight (before offering council):** check whether `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set (read `~/.claude/settings.json`). If the flag is missing:
     - **Skip the council offer entirely.** Run the meeting solo.
     - Name the loss explicitly: *"Agent Teams not enabled — running this meeting without multi-voice deliberation. To enable: run `/we:setup` or add `\"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS\": \"1\"` to the `env` block in `~/.claude/settings.json` and restart your session."*
   - If flag is present → proceed with the council offer as described above.
   - If convened → invoke the council via `Skill(skill="council", args="\"<framing question>\" --meeting=<type>")`. The topic and the `--meeting` flag are passed in the `args` string; the council skill parses them. Note: `/we:council` runs a live Agent Team since v2.31.0 — invoking it inline is correct, but it is not instantaneous; expect ~5 min wall-time per council convened. The roster for the type comes from `.weside/config.json` `council.meetings.<type>` (or the shipped default — see table below). Feed the synthesis into the meeting workflow.
3. **Run the meeting workflow** for the type (see the four sections below).
4. **Close out** — vision/saga/epic produce a written summary artifact (the final step of each workflow) and offer to persist it; story instead hands off to `/we:story` (Solo) per its workflow. The APO convention for persisted artifacts is the flat `docs/plans/` directory (e.g. `docs/plans/<saga>-saga.md`, `docs/plans/<saga>-<epic>-epic.md`) for Saga-and-below, `docs/plans/<vision>-prd.md` for the Vision.

## Default council rosters (shipped)

| Meeting | Default voices                                                    |
| ------- | ----------------------------------------------------------------- |
| vision  | product_owner, architect, ux_researcher, marketing, orchestrator  |
| saga    | product_owner, architect, marketing (or ux_researcher), orchestrator |
| epic    | product_owner, architect, orchestrator                            |
| story   | product_owner, architect                                          |

Override per repo in `.weside/config.json.council.meetings.<type>`, or per call with `--council=role,role,…`. See `we/skills/council/SKILL.md` for the role resolution path.

## Meeting: vision

**Frame:** *"Why does this product exist, and who is it for? Which Sagas does that imply?"*

1. Load the inputs — the existing PRD (`docs/plans/<vision>-prd.md`) if any, plus market / strategic context the user brings.
2. (Council) — convene if chosen; pressure-test the bets ("is the audience real?", "is the change ambitious enough?", "what are we ignoring?").
3. Identify candidate **Sagas** — coherent multi-quarter bets implied by the Vision.
4. Prioritise them with the user; mark which are active this year.
5. Artifact: a vision-meeting summary — the Sagas, the priorities, the reasoning. Offer to persist as `docs/plans/<vision>-vision-meeting-<YYYY-MM-DD>.md` or fold the Sagas into the PRD via `/we:vision`.

**Hand-off prompt** (printed to the user at close): *"The Sagas are named. Run `/we:vision` to sharpen the PRD with the new Saga bets, then `/we:saga "<name>"` per Saga to formulate each one."*

## Meeting: saga

**Frame:** *"Where do we want to be in twelve months on this Saga? Which Epics does it break into, in what order?"*

1. Load the Saga (`docs/plans/<saga>-saga.md`) or the working draft.
2. (Council) — convene if chosen; ask "does this Saga actually serve the PRD, or is it a side quest?" and "what are the 3-6 Epics that, in sequence, deliver the bet?".
3. Decompose the Saga into **Epics** — each a quarter-sized, finishable deliverable.
4. Sequence the Epics; name dependencies; identify the first one to commit to.
5. Artifact: a saga-meeting summary — the Epic set, sequencing, dependencies, open questions. Offer to persist as `docs/plans/<saga>-saga-meeting-<YYYY-MM-DD>.md` or fold the Epics into `SAGA.md` via `/we:saga`.

**Hand-off prompt:** *"The Epics are named and sequenced. Run `/we:saga` to lock the Saga doc, then `/we:epic "<name>"` per Epic to start formulating the first one."*

## Meeting: epic

**Frame:** *"What is the concrete thing we will deliver this quarter, and what Stories does it break into?"*

**When this meeting adds value:** the Epic scope is contentious or unclear; multiple architecture seams compete; you want multi-voice pressure-testing before committing to stories; the story sequencing is uncertain. **Skip it** when the Epic is well-formulated and stories are already sketched in the CONCEPT.md — go directly to `/we:story <KEY>` per Story instead.

1. Load the Epic — `docs/plans/<saga>-<epic>-epic.md`, or a ticketing-tool Epic, or the working topic.
2. (Council) — convene if chosen; pressure the slice ("is this the smallest version that delivers the win?", "what's the risk-driven sequence?", "where do we cut if the quarter runs short?").
3. Decompose the Epic into **Stories** — sprint-sized feature slices with acceptance shape.
4. Sequence the Stories; identify which one to refine first; flag any that need a Council pass via `/we:meet story`.
5. Artifact: an epic-meeting summary — the Story list with acceptance shape, sequencing, dependencies. Offer to persist as `docs/plans/<saga>-<epic>-epic-meeting-<YYYY-MM-DD>.md` or fold the Story breakdown into the Epic's `CONCEPT.md` via `/we:epic`.

**What this meeting produces vs. what you still need:** The meeting produces Story names and acceptance *shape* (rough AC, sequencing). You still need `/we:story <KEY>` per Story to write the build-ready implementation plan — the Council never produces that.

**Hand-off prompt:** *"The Stories are named. If the CONCEPT already reflects them, go directly to `/we:story "<name>"` per Story to write the build-ready plan. If not, run `/we:epic` first to fold the story breakdown into the CONCEPT, then `/we:story` per Story."*

## Meeting: story

**Frame:** *"Is this Story's scope clear, and what does the build-ready plan look like?"*

1. Load the Story — a ticket key, a draft, or a concrete topic.
2. (Council) — convene if chosen (default = offer); pressure-test scope and acceptance ("is the AC obvious?", "is there a defensible alternative implementation we should consider?", "what's the smallest version that still delivers user value?").
3. Consolidate the scope with the user — what is in, what is out, the shape of the Story.
4. **Hand off to `/we:story`:** print the instruction *"Scope is clear — now run `/we:story <ticket-or-topic>` to write the plan."*
   Do **not** call `Skill(skill="story")` inline — `/we:story` (Solo) is a large interactive skill; invoking it inline inflates context. The hand-off is an explicit instruction to the user.

The story meeting is the natural upgrade path for `/we:story` (Solo) when the Story is contentious enough to warrant two perspectives before the plan crystallises. For routine Stories, `/we:story` alone is fine.

## Rules

- **Always offer the council** (unless a flag decides) — never infer "complexity".
- **story hands off by instruction**, not by inline `Skill()` call. Same rule for vision/saga/epic when they hand off to the corresponding Solo skill.
- **Degrade gracefully** — no council configured, no weside: the council falls back to generic agents (handled by `/we:council`), or the meeting runs solo. If `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is missing, skip the council offer and run the meeting solo, naming the loss explicitly (see Step 2 env-flag preflight).
- A meeting produces **decomposition + a synthesis**, not code and not the artifact itself. The Solo skill at the same altitude writes the artifact; the Solo skill at the next altitude down picks up the decomposition.
- Implementation is `/we:build`. Meetings never call `/we:build`.

## References

- `we/skills/council/SKILL.md` — the deliberation engine a meeting convenes
- `we/skills/vision/SKILL.md` — Vision-altitude Solo
- `we/skills/saga/SKILL.md` — Saga-altitude Solo
- `we/skills/epic/SKILL.md` — Epic-altitude Solo
- `we/skills/story/SKILL.md` — Story-altitude Solo (what `/we:meet story` hands off to)
- `we/skills/build/SKILL.md` — Build pipeline (downstream of Story; not a meeting type)
- `we/skills/CLAUDE.md` — Activity-vs-Meeting design rationale
- [`docs/concepts/meetings.md`](../../../docs/concepts/meetings.md) + [`docs/concepts/companion-framework.md`](../../../docs/concepts/companion-framework.md) — methodology + council mechanic
