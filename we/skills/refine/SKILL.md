---
name: refine
description: >
  Writes a build-ready story plan from front-loaded context, with no user in the room — what a
  dispatched refiner runs. Triggers: "/we:refine", "refine this story without asking me".
---

# /we:refine

You turn a ticket plus the brief you were handed into the plan at the path the brief names (default
`<repo>/docs/plans/{TICKET}-story.md`), in the format of `${CLAUDE_PLUGIN_ROOT}/skills/story/references/plan-format.md`.
Dispatchers run you as `Agent(subagent_type: "we:dev-high")`: plan-writing is a named `dev-high` case (Foxy 27.09.).
There is no user to ask. What the brief, the ticket, the decision records and the code do not settle is an Open Fork, never a guess.
You write the plan file and nothing else: no commit, no push, no ticket write. Shell reads (`rg`, the code graph, `git log`) are fine.
Your final message is the report the dispatcher reads (step 5).

## Rules

- **No plan mode.** `EnterPlanMode` waits for an approval nobody gives.
- **Read before you assume.** The most frequent correction in past sessions was a wrong assumption about the
  environment or an earlier decision; step 2 lists where both live.
- **A genuine fork stops you.** Genuine: either branch changes user-visible behaviour no AC states, touches a
  subsystem the scope declares out, or contradicts a prior decision, and nothing you read settles it. An absent
  constraint is not a decision: "the epic didn't fund it, so I'll take the cheap one" is the rationalisation this
  rule catches.
- **Stopping is not writing nothing.** Write the plan as far as the fork allows, keep `status: draft`, and put
  `## Open Fork` directly after `## Context` (the format file says what goes in). Say in the section and in the
  report that the plan is not ready to dispatch; the refined scan passes such a plan mechanically.
- **The dispatcher verifies.** You proofread your file (step 4); running the DoR or claiming it passed is the
  dispatcher's job.

## Workflow

0. **Re-dispatch.** The plan already exists and the brief names what changed: edit only that, keep the rest,
   say in the report what you changed, and skip steps 1–2. A `MISSING:` item that already looks satisfied →
   report `blocked` with that sentence. An answered fork → write the phases it unblocks, record the decision
   and its author in `## Design Decisions`, and delete `## Open Fork`.
1. **Ticket with comments first** (`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`): one call, and a blocking
   question there can end the run early. A comment that contradicts the brief goes into `## Design Decisions` with both statements
   named, and the newest is built. No ticketing access → work from the brief and say so in `## Context`.
2. **Read before writing.**
   - The brief's refs, then the instruction file chain (`AGENTS.md`, else `CLAUDE.md`) and the repo rules for
     the paths the story touches.
   - ADRs and earlier plans on the same seam; the epic plan's `## Success Criteria` (older epics: `## Success Metrics`).
   - `.weside/dor.md`: each row becomes a labelled line in `## Constraints and Pins`.
   - `.weside/config.json`: `test_discipline` (`tdd`, `tests-after` as the default, `off`) sets the level of
     `## Testing Requirements`; `tools.graphify` and `tools.turbovault` say which search tools exist.
   - `.weside/verify.md` for the `## Verification` commands; absent → say so there and propose it under
     `## Documentation Impact`. A verb that cannot go red counts as missing.
   - The code: the seam the story names. With the code graph, `graphify affected "<identifier>" --relation calls
     --depth 2`; otherwise `rg`, and write "grep-derived, no code graph" into `## Technical Approach`. Resolve
     prose scope ("the queue producer and consumer") to real paths before listing them.
3. **Write the file.**
   - Real phases even for a small story: each independently committable, with its own `**Files:**` list
     (generated artifacts included; `rg` the changed symbols under the test trees for call sites that break) and
     a `**Risk:**` line.
   - `parallel_groups` stays `[]` unless phases have disjoint files and a fixed contract between them.
   - Every AC is `**Given** … **When** … **Then** …`, checkable against a running system, not against the diff.
   - The repo's markdown linter must accept the file, or the dispatcher's commit aborts silently. `.markdownlint*`
     decides; without one: prose wrapped at 80 columns, a blank line before every list (after `**Files:**` too),
     no wrap inside a code span or a table.
4. **Proofread.** `rg -n '^### Phase \d+: ' <plan>` and `rg -c '\*\*Files:\*\*' <plan>` match per phase; every AC
   carries `**Given**`, `**When**` and `**Then**` capitalised; `## Context` is a paragraph; the frontmatter lines
   are bare. Do the same after a step-0 edit.
5. **Report** as your final message, one of:

   ```text
   done: <absolute plan path> | ACs: <one line each> | phases: <N: title (risk)> | decisions not in the brief: <…> | conflict: <one line, if any> | fixed: <the MISSING item, on a re-run>
   blocked: <fork in one line> | A: <option + cost> | B: <option + cost> | recommend <X> because <why> | partial plan at <absolute path>, status draft, not ready to dispatch
   ```

   Running as an Agent Teams teammate instead, send the same text as one `SendMessage` to the lead; a
   teammate's plain text never reaches it.
