---
name: story
description: >
  Story (Solo) — PO skill at the Story altitude. Creates or refines one
  sprint-sized Story with a build-ready plan (ticket MINIMAL, plan
  DETAILED, EnterPlanMode). Use when the user says "/we:story",
  "new story", "refine story", "acceptance criteria".
  Contentious stories: /we:meet story first.
---


# Story (Solo) — Product Owner at the Story altitude

You produce or sharpen one Story — a sprint-sized feature slice with a build-ready plan. This is
the Solo half of the Story altitude; the Council half is `/we:meet story`, which hands off here.
Upstream `/we:meet epic` decomposes Epics into Stories; downstream the plan goes to
`/we:orchestrate {TICKET}`, which reads it as a dispatch contract. Altitude map:
[`docs/concepts/meetings.md`](../../../docs/concepts/meetings.md).

**Epic-altitude work** (formulating or refining an Epic) belongs to `/we:epic` (Solo) or
`/we:meet epic` (Council), never here.

---

## Prerequisites

```
Read("${CLAUDE_PLUGIN_ROOT}/quality/dor.md")
Read("${CLAUDE_PLUGIN_ROOT}/references/verification.md")
Read("${CLAUDE_PLUGIN_ROOT}/references/long-running.md")
```

**Repo-local DoR (additive):** resolve the repo root (`git rev-parse --show-toplevel`) and read
`<repo-root>/.weside/dor.md` if it exists — its rows apply *on top of* the plugin DoR, never
instead of it. Each repo-local row gets its own labelled line in the plan (`**<Row name>:** …`),
because `/we:orchestrate` gates on it and names the failing row.

**Glossary:** read `CONTEXT.md` at the repo root if it exists, and use its canonical vocabulary in
the **ticket and the plan** (never its `_Avoid_` terms).

---

## Your Output

| What | Where | Detail Level |
|---|---|---|
| User Story | Ticket (minimal) | "As X I want Y so that Z" |
| **Plan** | `docs/plans/{TICKET}-story.md` | Acceptance Criteria, Technical Approach, Phases, Tests |

`{TICKET}` is the ticketing key; with no ticketing tool it is a kebab-case slug of the story
title. The same token names the plan file, the frontmatter `story:`, the checkpoint and the
branch — pick it once, in Step 1, and never vary it. Detection:
`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`.

**Ticket is MINIMAL. Plan contains ALL details.**

## Modes

| Invocation | What changes |
|---|---|
| `/we:story {TICKET}` | refine an existing Story — all steps below |
| `/we:story "description"` | create: run Step 2 first, then create the minimal ticket (Step 5.3's body), then Steps 3–5 |
| `/we:story` (no argument) | ask what the user wants to build, then as above; if several Stories emerge, work them one at a time — establish the parent Epic first via `/we:epic` |

---

## Step 1: Load

Fetch the ticket from the ticketing tool — **including its comments** (they carry corrections and
agreed edge cases the description doesn't; newest statement wins on conflict):
`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`. Note the newest comment's id or timestamp; it
becomes the plan's `comments_read_through:`, which is how a later Lead tells "the comments have
overtaken this plan" from "this plan already answered them".

If `docs/plans/{TICKET}-story.md` exists, read it in full and refine **in place**, preserving its
Design Decisions rows; otherwise you are writing a new one.

## Step 2: Understand (INTERACTIVE)

Clarify scope, requirements and edge cases **grill-style**: one question at a time, each with your
recommended answer, and read the codebase for anything discoverable there. When a fuzzy or
conflicting term gets resolved, offer to record it in the project glossary (`CONTEXT.md`, see
`/we:grill`) — offer to create the file if it does not exist, and write it in Step 5.1's commit.

If `.weside/vision.md` exists, or a Companion is connected via weside MCP, check the story against
it and name any tension you find. No vision configured → skip silently.

**Brainstorming first if requirements are vague.** When the summary is vague or the "why" is
unclear, establish intent BEFORE scoping ACs. With the `superpowers` plugin available, invoke its
`brainstorming` skill; otherwise ask targeted questions — "What does success look like?", "What
are you actually trying to enable?", "What's the simplest version of this?". Scope ACs only once
you understand the goal.

**When the work feels too big for one build pass, ask *which* kind of big.** Two shapes hide
under "too big":

- **Many independent slices** (separate features, separate user value, separate PRs) → genuinely
  Epic-sized. Do not research further: write the slice cut, the sequencing constraint and the
  decision (including the alternative the user rejected, and why) as a ticket comment, print —
  never invoke — `/we:epic {TICKET}`, and STOP. If no parent Saga exists, say so in the same
  line; `/we:epic` will ask for one.
- **One coherent change with several phases** (a refactor, a multi-layer fix, a migration) → this
  stays a **single Story** with a phased plan, run by `/we:orchestrate {TICKET}`. Splitting a
  coherent change into N stories just to dispatch it multiplies overhead the work does not need;
  the phase decomposition and `parallel_groups` carry the structure instead.

The urge to split into phases is the orchestrate signal, not the epic signal.

## Step 3: Create Plan (EnterPlanMode)

**Architecture context.** With TurboVault MCP:

```
mcp__turbovault__semantic_search("topic of this story")
mcp__turbovault__advanced_search(query, frontmatter_filters=[{key:"domain", value:"<relevant-domain>"}])
```

Without it, say once — "⚠️ TurboVault unavailable — using grep fallback; architecture context may
be incomplete. Check the MCP config." — then `Grep(pattern="<topic keyword>", include="*.md")` and
`Glob(pattern="docs/architecture/**/*.md")`. Reference what you find in the plan's Technical
Approach.

**Blast radius.** When `.weside/config.json` → `tools.graphify` is true, ground the per-phase
`Files:` lists and the `parallel_groups` decision in the code graph — identifier-style terms
(`ChannelAdapter`, `DispatchService`), not prose:

```bash
graphify affected "<identifier>" --relation calls --depth 2
```

When the flag is false or absent, derive the lists with `rg` on the same identifiers and write
"`Files:` lists are grep-derived — no code graph" into the plan's Technical Approach, so the Lead
knows how much the disjointness guard is worth.

**Session context → plan.** Distil the conversation into the Context section (a narrative brief
for a colleague who wasn't in the room — the most important section for the implementing agent)
and into the Design Decisions table (every alternative discussed and why it was rejected). Load
more files than feel necessary; a wrong assumption costs more than a wide read.

```markdown
---
type: story-plan
story: {TICKET}
epic: {EPIC-SLUG-OR-KEY}  # REQUIRED when the story belongs to an Epic — /we:orchestrate's ready-set filters on it, and a missing epic: makes the story invisible. Omit only for standalone stories.
depends_on: []            # optional: story keys that must merge first
comments_read_through: {newest comment id or timestamp, or "none"}
created: YYYY-MM-DD
status: draft
parallel_groups: []       # optional: [[N, M, ...], ...] — see the independence check below
---

# Plan: [Story Title]

## Context

[Narrative brief, 3-8 sentences, no bullets: what problem, why NOW, what the user cares about
most, constraints that aren't obvious from the code, what the design discussion settled.]

## Acceptance Criteria
1. **Given** [context] **When** [action] **Then** [result]

## User Journey
> **This story is only DONE when the user can experience the journey end-to-end.**

1. [Starting point] 2. [Action] 3. [Result] 4. [Close]

## Testing Requirements
- Unit tests for [X]
- Integration tests for [Y] — name the runnable suite and the database, not just the type

## Verification
> How this will be observed running — not inferred from green tests. The build turns this into
> the PR's `## Verification` receipt. See `references/verification.md`; commands live in
> `<repo>/.weside/verify.md` — absent → say so once and propose it under Documentation Impact.

- **Oracle:** cli | ui | substitute | not-applicable — *why this one*
- **Seed:** [the command that puts the system in the state to observe]
- **Asserted:** [what has to be true — endpoint + field, or route + label]
- **Not proven:** [what this oracle cannot show, and who owes it]
- **Exit criterion:** [what someone else could run to decide "done"]
- **Missing CLI verb:** [name it if the seed needs a shell dance — and say which phase ships it,
  as early as that phase's own dependencies allow; if it cannot be first, say why]

## Technical Approach
**Patterns:** [relevant patterns]

## Implementation Phases

### Phase 1: [Name]
- **Goal:** [achieved outcome]
- **Files:** [affected files — including what the change *causes* to change: generated artifacts
  (OpenAPI spec, generated clients, snapshots) and the existing test files whose call sites it
  breaks (`rg` the symbol under the test trees)]
- **Risk:** ordinary | migration | money | auth | tenant-isolation — [why]
- **Approach:** [how]

### Phase 2: [Name]
...

## Constraints and Pins
**Constraints:** [conventions and primitives this change must compose]
**Pins:** [existing behaviour that must not change, named precisely enough to conflict against]

## Design Decisions

| Decision | Alternatives Considered | Why This |
|----------|------------------------|----------|
| [what we chose] | [what we didn't choose] | [reasoning] |

## Code Guidance
**DO:** [pattern to follow]
**DON'T:** [anti-pattern to avoid]

## Security Review Required
[Yes/No] — [reason]

## Documentation Impact
> Where does the knowledge land? A cascade — most stories stop at the first line, and
> "the code carries it" is a complete answer. Full contract: `quality/dod.md` § Documentation.

- **Docstrings** — [which files/symbols hold the reasoning once this lands — the default]
- **Architecture doc** — [only if interplay across modules changes: which doc, what changes]
- **ADR** — [only if hard to reverse ∧ surprising ∧ a real trade-off]
- **Generated** — [API spec/types, CLI reference, registers to regenerate]
- **New doc** — [name it only with the reason the code cannot hold it]
```

> **Always decompose into real phases — even for a small story.** A phase is a self-contained,
> independently-committable chunk with its own `**Files:**` list; the phases ARE the structure
> both downstream skills read. Don't collapse a multi-step change into one mega-phase.
>
> **Independence check (fill `parallel_groups`):** phases with **disjoint files** and **no
> ordering dependency** may share a group — e.g. `parallel_groups: [[2,3]]`. `/we:orchestrate`
> reads a group as: every phase outside a group runs serially in plan order, a group starts only
> after every lower-numbered phase has **merged**, and at most 2 chunks run concurrently inside
> it. Size groups accordingly, and when in doubt keep the list empty — prose like "these can run
> in parallel" is invisible to the consumer.

## Step 4: User Approval (ExitPlanMode)

User reviews the plan. On feedback → adjust and present again. On approval → Step 5 immediately.

## Step 5: Post-Approval — EXECUTE IMMEDIATELY

⛔ **ExitPlanMode approval means "run Step 5", not "stop and summarize".** Run these in order.

0. **Resolve the main worktree** — the plan belongs where `main` is checked out, not in the
   feature worktree you may be standing in:
   ```bash
   MAIN_WORKTREE=$(git worktree list --porcelain | awk '/^worktree /{p=$2} /^branch refs\/heads\/main$/{print p; exit}')
   ```
1. **Save plan:** write the approved plan to `$MAIN_WORKTREE/docs/plans/{TICKET}-story.md` with
   `status: approved` and `story: {TICKET}` in the frontmatter. (`~/.claude/plans/` is temporary;
   `docs/plans/` is permanent.) Write the accepted `CONTEXT.md` glossary entry, if any, now.
2. **Scan what you wrote:** run the 3-item check in
   `${CLAUDE_PLUGIN_ROOT}/references/dor-scan.md` against the file. A failure means fix the plan
   — never skip ahead to the checkpoint.
3. **Ticket, in one pass** (`references/ticketing.md` — transition first, comment second, verify
   the move): set the description to the minimal body below, add ONE comment naming each
   contradiction you resolved and each question you parked, and transition the ticket to the
   repo's ready state. No ticketing tool → skip silently.
   ```markdown
   ## User Story
   As [role] I want [feature] so that [benefit].

   ## Plan
   Implementation Plan: docs/plans/{TICKET}-story.md
   ```
   Anything beyond this template follows `${CLAUDE_PLUGIN_ROOT}/references/ticket-briefs.md` for
   *wording* — behavioural, durable, no file paths or line numbers.
4. **Commit the plan** — one failure mode per message, so a wrong diagnosis never sends the
   reader to the wrong place:
   ```bash
   [ -n "$MAIN_WORKTREE" ] || { echo "WARN: no worktree on main — plan saved, not committed."; exit; }
   cd "$MAIN_WORKTREE" || exit
   git add docs/plans/{TICKET}-story.md && \
     git commit -m "docs: add {TICKET} plan — {Story Title}" || \
     { echo "WARN: commit failed (hook rewrite?) — re-add and commit by hand."; exit; }
   git push || echo "WARN: committed locally, push failed (branch protection?) — push by hand."
   ```
5. **Checkpoint:** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint {TICKET} refined`
   (the CLI keeps the `story` table name for back-compat).
6. **Vault links (TurboVault only):** run `mcp__turbovault__suggest_links` on the new plan doc and
   offer each suggestion `[y/n]`. Skip silently without TurboVault.
7. **Output + execution-surface recommendation** — decide dispatched vs. `--solo` per the
   *Execution Surface* heuristic below, then emit:
   ```
   Plan saved to docs/plans/{TICKET}-story.md. /we:story DONE.
   State file: docs/plans/{TICKET}-state.md (the Lead creates it on the first run).

   Recommended next: /we:orchestrate {TICKET}   ← <one-line why: phases N, parallel waves {…}, or context-hygiene>
   (or /we:orchestrate {TICKET} --solo if you'd rather run it inline.)
   ```
   Lead with the recommended shape and name the phase count plus which phases parallelise. Print
   the `/loop` (or, at its bar, `/goal`) invocation when `references/long-running.md`'s trigger
   fires — printed, never invoked, and only once the plan's `## Verification` names a scriptable
   oracle. If the oracle is not scriptable yet, say so and make the first round's job to make it so.

⛔ **STOP after Step 5.** Story + Plan is the whole job — no implementation, no branch, no
auto-continue to `/we:orchestrate`. The user invokes the next surface.

---

## Execution Surface — recommend dispatched vs. `--solo`

Both run the same plan through the same pipeline; they differ in *who holds the work*.

| | `/we:orchestrate {TICKET} --solo` | `/we:orchestrate {TICKET}` (phase dispatch, Mode B) |
|---|---|---|
| **Shape** | one autonomous pass in the caller's session | Lead dispatches each phase as a work-chunk, integrates onto one branch, runs CI once → one PR |
| **Best for** | trivially straight-line work — one phase, small diff | anything worth splitting into phases; parallelisable phases; a coherent change big enough that inline would bloat the caller's context |
| **Caller's context** | fills with the whole implementation | stays clean — reports and the final PR, not every diff |
| **Review stance** | caller is also the implementer | caller reviews **neutrally** (didn't write it) |

**Recommend `/we:orchestrate`** when ANY holds: the plan has 2+ real phases; `parallel_groups` is
non-empty; it is a coherent multi-layer/refactor/migration change; or the caller benefits from
context-hygiene plus neutral review (true even for a *small monolith*). **Recommend `--solo`**
only for a genuinely trivial, straight-line single-phase story — a typo, a one-function fix, a
config tweak — where dispatch overhead buys nothing.

---

## Rules

- The plan filename suffix is `-story.md` (legacy `-plan.md` still read for back-compat).
- **Plans are living.** When the story belongs to a multi-wave programme, its DoD includes
  rewriting this plan to match what was actually BUILT before the PR merges, and updating
  `docs/plans/<epic>-state.md` in the same PR — the next agent reads the plan, not the diff, and
  after a compact that agent is you. See
  `${CLAUDE_PLUGIN_ROOT}/references/programme-discipline.md`.
- **User-visible surfaces owe a proof block.** If the story changes something a user sees, its
  `## Verification` names how it will be checked against a RUNNING app and what stays owed
  without a manual round — "tests are green" is a claim about units, not about the app.
