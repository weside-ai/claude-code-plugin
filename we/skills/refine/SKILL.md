---
name: refine
description: >
  Write a build-ready story plan from front-loaded context, with no user in the
  room — the non-interactive counterpart to /we:story, and what an orchestrated
  refine-worker runs. Use when the user says "/we:refine", "refine this story
  without asking me", or when a Lead dispatches a refiner.
---

# /we:refine

Turn a ticket plus the context you were handed into `docs/plans/{TICKET}-story.md` that passes the
DoR scan. **There is no user to ask.** Everything needed is in the brief or in the repo; if it
isn't, you say so rather than invent it.

**`/we:story` is the interactive path** — it asks the questions, sharpens the glossary, and stops
at a plan-mode gate. Reach for it when a human is present and the scope is genuinely open. This
skill is the other case: the scope is settled, the context is written down, and what's missing is
the plan file.

## Hard rules — these are what make it dispatchable

- **Write the plan file. Run nothing else.** No `git`, no `gh`, no `orchestration.py`, no
  checkpoint, no commit. A dispatched refiner is often running under a permission mode that denies
  teammate Bash outright, and a refiner that needs a shell is a refiner that dies on its first
  command.
- **Never enter plan mode.** `EnterPlanMode`/`ExitPlanMode` wait for a human approval that will
  never come when you were dispatched. Draft in your head, write the file.
- **The Lead verifies, not you.** Don't claim the plan is refined and don't run the DoR scan on
  your own output — report the path and let whoever asked check it. State-as-truth cuts both ways:
  your "done" is a claim, the scan is evidence.
- **A genuine design fork stops you.** If the context cannot settle a real decision — which of two
  seams, whether an interface is frozen — say so and stop. A guessed fork produces correctly-built
  wrong code, which costs more than the question would have.

## What you write

The frontmatter (`story`, `epic`, `created`, `status: draft`) and these sections. The first three
are the gate — `references/dor-scan.md` is what will be run against your file:

- [ ] `## Context` — a real narrative brief, over 50 words: why this exists, where the seam is,
      what done looks like. One line fails the scan and, worse, tells the builder nothing.
- [ ] `## Acceptance Criteria` — numbered, each one `**Given** … **When** … **Then** …`. Write
      criteria a reviewer can check against a running system, not against the diff.
      **Capitalise all three keywords, every time.** The Definition-of-Ready scan matches the
      literal strings `Given`, `When` and `Then`; a lowercase `**when**` mid-sentence reads
      perfectly and leaves the plan stuck in `draft` with no error message anywhere. Measured
      2026-07-30: four consecutive plans, all complete, all rejected by the scan for this alone
      — the failure is silent by construction, because the plan looks right to every human who
      opens it.
- [ ] `## Implementation Phases` — `### Phase 1`, `### Phase 2`, … each with a concrete
      `**Files:**` list. Those lists are what the Lead's disjointness check reads before it dares
      run two workers at once; vague ones make the check lie.
- [ ] `## Technical Approach` — the patterns and files, reuse over rebuild.
- [ ] `## Design Decisions` — the real forks and why this option, so the builder doesn't
      relitigate them.
- [ ] `## Testing Requirements` — per AC, at the level `.weside/config.json`'s `test_discipline`
      asks for.
- [ ] `## User Journey`, `## Code Guidance`, `## Security Review Required`,
      `## Documentation Impact`.

Full template and field semantics: [`docs/plan-format.md`](../../../docs/plan-format.md).

**Write the plan so its repo's markdown linter accepts it.** The Lead has to commit the file, and
a pre-commit markdownlint that rejects it turns a finished plan into a silent abort — the commit
does not land and nothing says why until someone checks `git log`. Two rules cause nearly all of
it: **wrap prose at 80 columns**, and **leave a blank line before every list**, including one that
follows a bold lead-in like `**Files:**`. Wrapping inside a code span or a table is worse than a
long line — leave those alone. If the repo ships a config, its numbers win over these; check
`.markdownlint*` before assuming 80.

**Phases are the structure, not decoration.** Cut the work into independently-committable chunks
even when the story is small — that's what lets the Lead dispatch them, and it sharpens the plan
either way. Where phases touch disjoint files with no ordering dependency, declare them in
`parallel_groups` frontmatter; in doubt, leave it empty and let them run sequentially.

## Workflow

1. **Read what you were given, then read the code it names.** The brief's architecture references
   first, then the files the story will touch. A plan written without opening the seam it plans to
   change is a guess in plan format.
2. **Check the ticket's comments, not just its description** — corrections and scope cuts live
   there, newest wins, and you name the conflict rather than silently picking
   (`references/ticketing.md`). No ticketing access → work from the brief alone and say so in
   `## Context`.
3. **Write the file** at `docs/plans/{TICKET}-story.md`.
4. **Report the path** and nothing else. Dispatched into a team, that means exactly one
   `SendMessage` to `team-lead`:
   `summary="refiner-{TICKET} done|blocked"`,
   `message="wrote docs/plans/{TICKET}-story.md | blocked: <the fork>"`. Your plain-text output is
   invisible to a Lead — a report you didn't send is a story that never leaves the queue.

## References

- `references/dor-scan.md` — the 3-item scan your file has to pass
- `${CLAUDE_PLUGIN_ROOT}/quality/dor.md` — the full Definition of Ready
- `we/skills/story/SKILL.md` — the interactive path, when a human is in the room
- `we/skills/orchestrate/SKILL.md` — the Lead that dispatches this
