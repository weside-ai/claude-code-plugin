---
name: refine
description: >
  Writes a build-ready story plan from front-loaded context, with no user in the room — what a
  dispatched refiner runs. Triggers: "/we:refine", "refine this story without asking me".
---

# /we:refine

Turn a ticket plus the context you were handed into `docs/plans/{TICKET}-story.md`. **There is no
user to ask** — `/we:story` is the interactive path. Everything needed is in the brief or in the
repo; if it isn't, you say so rather than invent it.

## Hard rules — these are what make it dispatchable

- **Mutate nothing but the plan file.** Reads are expected — files, `Glob`, `Grep`, the ticket —
  but no shell: no `git`, no `gh`, no `orchestration.py`, no checkpoint, no commit. A dispatched
  refiner often runs where teammate Bash is denied outright, and one that needs a shell dies on
  its first command.
- **Never enter plan mode.** `EnterPlanMode`/`ExitPlanMode` wait for an approval that never comes.
- **The Lead verifies, not you.** Reading your own file back is proofreading and expected; running
  the DoR scan on it, or claiming it passed, is not.
- **A genuine design fork stops you.** Genuine = either branch changes user-visible behaviour no
  AC states, or touches a subsystem the scope declares OUT, or contradicts a prior decision — and
  nothing in the brief, the ticket, the ADRs or the code settles it. An *absent* constraint is not
  a decision: "the epic didn't fund it, so I'll do the cheap one" is exactly the rationalisation
  this rule exists to catch.

  Stopping is not writing nothing. Write the plan as far as the fork allows, leave
  `status: draft`, and put an `## Open Fork` section **directly after `## Context`**: the question
  in one line, option A and option B with their consequences, your recommendation and why. It goes
  there, not in `## Design Decisions`, because that section records decisions *taken*.

  The section is the file's own stop sign: such a plan passes the 3-item scan mechanically, so
  nothing but the section and your `blocked` report keeps it out of a wave — say in both that the
  plan is **not** ready to dispatch. `/we:develop` stops on it too.

## What you write

Frontmatter and section semantics are owned by [`docs/plan-format.md`](../../../docs/plan-format.md)
— follow it. What the sections owe:

- [ ] `## Context` — a real narrative brief: why this exists, where the seam is, what done looks
      like.
- [ ] `## Acceptance Criteria` — numbered, each one `**Given** … **When** … **Then** …`.
      Criteria a reviewer can check against a running system, not against the diff.
      **Capitalise all three keywords in every AC.** The scan only checks that the three tokens
      appear *somewhere* in the file, so it will not catch a lowercase `**when**` — the reviewer
      and `/we:develop` will, and a plan whose ACs read as prose is unbuildable.
- [ ] `## Implementation Phases` — `### Phase 1: <title>`, `### Phase 2: <title>`, … each with a
      concrete `**Files:**` list — the Lead's disjointness check reads them. When the brief gives
      scope as prose ("the queue producer and consumer"), resolve it to real paths with
      `Glob`/`Grep` first and say in `## Technical Approach` how.
- [ ] `## Technical Approach` — the patterns and files.
- [ ] `## Design Decisions` — the real forks and why this option, so the builder doesn't
      relitigate them. A ticket comment that contradicts the brief goes here, both statements
      named, newest built.
- [ ] `## Testing Requirements` — per AC, at the level `test_discipline` asks for
      ([`${CLAUDE_PLUGIN_ROOT}/references/test-discipline.md`](../../references/test-discipline.md)
      owns what each level means).
- [ ] `## User Journey`, `## Code Guidance`, `## Security Review Required`,
      `## Documentation Impact` — the last asks *where the knowledge lands* (`quality/dod.md`
      § Documentation). A docstring at the site is the usual answer; naming a new doc means naming
      why the code cannot hold it.

**Write the plan so the repo's markdown linter accepts it** — a rejected file aborts the Lead's
commit silently. `Glob` for `.markdownlint*`; without one: wrap prose at 80 columns, a blank line
before every list (including after `**Files:**`), never wrap inside a code span or a table.

**Cut the work into independently-committable phases even when the story is small** — that is what
lets the Lead dispatch them. Phases touching disjoint files with no ordering dependency go in
`parallel_groups`; in doubt leave it empty and let them run sequentially.

## Workflow

0. **Does `docs/plans/{TICKET}-story.md` already exist?** Then this is a re-dispatch and the brief
   names what changed — edit only that, keep the rest, say in the report what you changed, and skip
   steps 1–2. A `MISSING:` item that already looks satisfied → report `blocked` with that sentence,
   not a second guess. An answered fork → write the phases it unblocks, record the decision and its
   author in `## Design Decisions`, and **delete the `## Open Fork` section** — it is what stops
   `/we:develop`.
1. **Read the ticket and its comments first.** One call, and a blocking question there can end the
   run cheaply (`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`). Newest statement
   wins; you name the conflict in `## Design Decisions` rather than silently picking. No ticketing
   access → work from the brief alone and say so in `## Context`.
2. **Read the brief's architecture refs, then the code they name** — locate the seam from the refs
   and the repo's `CLAUDE.md`, then `Grep` the route or symbol the story names.
3. **Write the file** at `docs/plans/{TICKET}-story.md`, then `Grep` it back — `Given`, `When`,
   `Then` capitalised in *every* AC, `^### Phase \d+` for the headers, `**Files:**` under each —
   and read `## Context` to confirm it is a paragraph. Do the same after a step-0 edit.
4. **Report.** Dispatched into a team, exactly one `SendMessage` to `team-lead`
   (`ToolSearch` for it first):
   `summary="refiner-{TICKET} done|blocked"`. These templates extend the brief's — where the brief
   gives one slot and this gives five, send the five; a Lead reads fields, not a fixed string:

   ```
   message="wrote docs/plans/{TICKET}-story.md | fixed: <the MISSING item, if a re-run> | conflict: <one line, if any>"
   message="blocked: <fork in one line> | A: <option + cost> | B: <option + cost> | recommend <X> because <why> | partial plan at docs/plans/{TICKET}-story.md"
   ```

   Your plain-text output is invisible to a Lead.

## References

- [`${CLAUDE_PLUGIN_ROOT}/references/dor-scan.md`](../../references/dor-scan.md) — the 3-item scan the Lead runs on your file
- [`${CLAUDE_PLUGIN_ROOT}/quality/dor.md`](../../quality/dor.md) — the full Definition of Ready (its ticket half is the Lead's, not yours)
- [`${CLAUDE_PLUGIN_ROOT}/references/test-discipline.md`](../../references/test-discipline.md) — what each `test_discipline` level asks of `## Testing Requirements`
- `/we:story` — the interactive path, when a human is in the room
- `/we:orchestrate` — the Lead that dispatches this
