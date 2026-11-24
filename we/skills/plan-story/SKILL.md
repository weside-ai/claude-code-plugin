---
name: plan-story
description: >
  Writes a build-ready story plan from front-loaded context, with no user in the room — what a
  dispatched refiner runs. Triggers: "/we:plan-story", "refine this story without asking me".
needs: [ticketing]
---

# /we:plan-story

You turn a ticket plus the brief you were handed into the plan at the path the brief names (default
`<repo>/docs/plans/{TICKET}-story.md`), in the format of `${CLAUDE_PLUGIN_ROOT}/references/story-plan.md`.
Dispatchers run you as a `we:dev-high` worker: plan-writing is a named `dev-high` case (`references/worker-dispatch.md` § Choosing the worker).
There is no user to ask. What the brief, the ticket, the decision records and the code do not settle is an Open Fork, never a guess.
You write the plan file, for `receipt` ACs the repo's staging-check file next to it (step 3), and the token
line in the plan (step 5), nothing else: no commit, no push, no ticket write. Shell reads (`rg`, the code graph,
`git log`) are fine. Your final message is the report the dispatcher reads (step 6).
**A brief that makes the plan a PR chunk** (it names the commit or plan-PR command) overrides the no-commit
line: you commit and open the PR by that command, and the chunk ends at its merge (L0 § Workers): you watch it
until green, answer its review and Ready-panel rounds on the same branch, then report. **A brief that says `carry to
Selected`** runs § Carry to Selected after step 5 and ends with its report. Without such a line the
report ends you.

## Rules

- **No plan mode.** `EnterPlanMode` waits for an approval nobody gives.
- **Read before you assume.** The most frequent correction in past sessions was a wrong assumption about the
  environment or an earlier decision; step 2 lists where both live.
- **A genuine fork stops you.** Genuine: either branch changes user-visible behaviour no AC states, touches a
  subsystem the scope declares out, or contradicts a prior decision, and nothing you read settles it. An absent
  constraint is not a decision: "the epic didn't fund it, so I'll take the cheap one" is the rationalisation this
  rule catches.
- **The ticket's "done when" and scope bound the plan.** Work beyond them never becomes a phase; it goes into
  `## Out of scope` as a named follow-up. Splitting it off is not a fork; follow-ups are named, not filed
  (`references/worker-dispatch.md` § Dev-only worker contract). New visible behaviour no AC of the ticket states goes, in the same run, as one
  entry under the epic's `## Extensions` (`references/epic-plan.md` § Finish line), never as an AC of this plan.
- **A correction story lists every site before Ready:** `references/story-plan.md` § Out of scope.
- **Stopping is not writing nothing.** Write the plan as far as the fork allows, keep `status: draft`, and put
  `## Open Fork` directly after `## Context` (the format file says what goes in). Say in the section and in the
  report that the plan is not ready to dispatch; the Ready gate refuses such a plan.
- **A specialist's answer that changes what a user sees is a product decision.** Before the report, send it to
  the crew's product role as a proposed business AC (`<when> → <the user sees>`), checked against your
  `## Technical Approach` (the approach delivers exactly that), and name it in the report under `decisions not
  in the brief`; never take it into the plan as settled on the specialist's word alone.
- **One message per owner.** Read the ticket, the draft and the touched code first (step 2), then send each owner
  one message with every question for them, numbered, each with a recommendation, with the answer address
  (L0-worker). Good: one message with three numbered questions to the UX owner. Bad: six
  single-question rounds to the same owner while reading on. A later question to the same owner says why
  step 2 could not show it.
- **No presumed sign-off.** A pending owner question stands in the plan as `open, recommendation <session>`
  until the owner answers; only an explicit owner message becomes `<owner> <date>` in `## Design Decisions`.
- **The dispatcher verifies.** You proofread your file (step 4); running the DoR or claiming it passed is the
  dispatcher's job.

## Workflow

0. **Re-dispatch.** The plan already exists and the brief names what changed: edit only that, keep the rest,
   say in the report what you changed, and skip steps 1–2. First `git fetch origin` and run step 4's
   `check-plan-identifiers.py`: each `exists:` name is marked `(new)` or `(not on main)` yet main carries it now;
   rewrite its phase to build on main's version (good: "extend `ThreadLock` in `app/lock.py`"; bad: a second
   `ThreadLock (new)`). A `MISSING:` item that already looks satisfied →
   report `blocked` with that sentence. An answered fork → write the phases it unblocks, record the decision
   and its author in `## Design Decisions`, and delete `## Open Fork`.
1. **Ticket with comments first** (`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`): one call, and a blocking
   question there can end the run early. A comment that contradicts the brief goes into `## Design Decisions` with both statements
   named, and the newest is built. No ticketing access → work from the brief and say so in `## Context`.
2. **Read before writing.**
   - The brief's refs, then the instruction file chain (`AGENTS.md`, else `CLAUDE.md`) and the repo rules for
     the paths the story touches.
   - ADRs and earlier plans on the same seam; the epic plan's `## Success Criteria` (or `## Success Metrics`).
   - `.weside/dor.md`: each row becomes a labelled line in `## Constraints and Pins`.
   - `.weside/config.json`: `test_discipline` (`tdd`, `tests-after`, `off`) sets the level of
     `## Testing Requirements`; quote the value you read, never a default (bad: "the repo default
     (`tests-after`)" in a `tdd` repo; good: "`test_discipline: tdd` (.weside/config.json)"); key absent or
     file unreadable → say so there. With `tdd` every phase gets its `**Test first:**` line.
     Which tests, and how many: `${CLAUDE_PLUGIN_ROOT}/references/test-economy.md`.
     `tools.graphify` says whether the code graph exists.
   - `.weside/verify.md` for the `## Verification` commands; absent → say so there and propose it under
     `## Documentation Impact`. A verb that cannot go red counts as missing.
   - The code: the seam the story names. With the code graph, `graphify affected "<identifier>" --relation calls
     --depth 2`; otherwise `rg`, and write "grep-derived, no code graph" into `## Technical Approach`. Resolve
     prose scope ("the queue producer and consumer") to real paths before listing them.
   - Four claim classes drew most of the Lead's corrections: a claim over a
     set ("every table", "all five call sites") lists each member with file:line; a new lookup into an existing
     map names the keys its callers pass and what a miss does; every caller of the changed seam is traced and
     each path that skips the new guard is named; every behaviour change on an existing path is an AC or a
     `## Design Decisions` line.
   - A plan that maps an external format (an import, an export, a foreign API) lists that schema's required
     fields, each with the field it lands in (good: "`original` → `source_text`"; bad: "map the fields"), read
     from the schema itself, never from a sample file.
   - A new table names its row-access form per the repo's auth doc (an ownership-join policy, or no
     policy plus the bypass call at each call site) and, for rows that expire, the job and batch that
     delete them (an allow-all policy and no purge passed three panels, two review rounds later).
3. **Write the file.**
   - Sections, phases (`**Files:**`, `**Repo:**`, `**Risk:**`), AC form and oracle-class marker:
     `${CLAUDE_PLUGIN_ROOT}/references/story-plan.md`. A defect at one place takes its § Short form; the gate
     says when it needs the full form. Real phases even for a small full-form story, each independently
     committable; `rg` the changed symbols under the test trees for call sites that break. Every AC is checkable
     against a running system, not against the diff. A parity oracle compares against a reference
     outside the code under test (good: "equal to the recorded host request"; bad: "equal to the other
     turn's body" when both run through one serializer). A sentence users read about privacy, retention, consent,
     security or a crisis carries, in its AC, the verdict of the crew member with `specialist: legal` where the crew has one.
   - Every `receipt` AC gets its check in the staging-check file `.weside/verify.md` names, in the planned state it
     names, check id `AC<n>` (story-plan.md § Verification); `**Staging checks:**` names the file. A repo whose
     `.weside/verify.md` names no staging checks gets no file and no `receipt` marker.
   - The repo's markdown linter must accept the file, or the dispatcher's commit aborts silently. `.markdownlint*`
     decides; without one: prose wrapped at 80 columns, a blank line before every list (after `**Files:**` too),
     no wrap inside a code span or a table.
4. **Proofread.** Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ready_gate.py story <plan>` and fix each line it
   prints; `## Context` is a paragraph. A `scope change:` line no edit of yours fixes: send the fence change
   to the approver it names in this run (`SendMessage`, or the report's `decisions not in the brief`), and
   report `blocked` on it, never `done`, while the gate prints it. Then `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check-plan-identifiers.py <plan> --ref origin/<default>`:
   each `missing:` name is struck, corrected, or marked `(new)` when the plan builds it; each `exists:` name
   loses its `(new)` and the plan builds on main's version. With a staging-check
   file, run the validate command `.weside/verify.md` names on the plan until it exits 0. Do the same after a
   step-0 edit.
5. **Token line.** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/session_tokens.py --plan <plan> --step refine` as the
   last write, also after a step-0 edit; it always exits 0 and writes `absent (<reason>)` when it cannot measure.
6. **Report** as your final message, one of:

   ```text
   done: <absolute plan path> | staging checks: <absolute path | none> | ACs: <one line each> | phases: <N: title (risk)> | decisions not in the brief: <…> | conflict: <one line, if any> | fixed: <the MISSING item, on a re-run>
   blocked: <fork in one line> | A: <option + cost> | B: <option + cost> | recommend <X> because <why> | partial plan at <absolute path>, status draft, not ready to dispatch
   ```

   A brief with a `Lead:` line, or running as an Agent Teams teammate: send the same text as one
   `SendMessage` to the Lead; your plain text never reaches it.

## Carry to Selected

The brief makes you land the plan and take it through the Ready panel; step 6's report comes at the end of
this section, never between. A fork or a `scope change:` line still ends you with `blocked` at step 6.

1. **Approve.** Set `status: approved`; `ready_gate.py story <plan>` exits 0 (step 4), or you fix and rerun.
2. **Land** per `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md` steps 4–5 from your own tree (a worktree off
   the default branch, so no scratch tree): its `check-plan-identifiers.py` is the check of your code claims,
   no other pass follows. By push, `plan_push.py` exits 0. The PR way: open the docs PR, send its URL to your
   starter in one line (a worker never arms; the starter does), and wait in the background with
   `watch-pr-checks.sh <PR> --until-merged` for `merged`.
3. **Panel, only for a risk plan.** Try step 5 first: `board.py select` takes a plan whose computed tier is
   `T0` without a panel. Refused in group `lenses`: Skill tool, skill `we:lens`, args `ready <KEY>`; you run its steps.
4. **Fix within the cap.** A red round: fix every BLOCKING and WARNING finding of it in one edit, rerun steps
   1–2, then step 3 again. `round cap: the lens holder decides` ends the loop: no further edit, report `capped`.
5. **Select.** Green: first read the crew switch, `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/crew.py show`; when its
   `select.refiner` is `false` the product role selects every story, so skip the call and report
   `selected: no, product selects (the crew sets select.refiner: false)`. Otherwise
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board.py select <KEY> --refiner`, always with
   `--refiner`; its `carry:` line is yours to carry per `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md` (move,
   then read back). Refused in group `refiner` (no approved epic line holding the key, or the epic says
   `select: owner`: `${CLAUDE_PLUGIN_ROOT}/references/epic-plan.md` § Finish line) or `role`: report
   `selected: no, <role> selects (<board.py's reason line>)`, never retry.
6. **Report**, one of:

   ```text
   selected: <KEY> | plan: <path on the default branch> | rounds: <n> | decided: <lens: sentence | none> | <step 6 fields>
   capped: <KEY> | rounds: <n> | holder decides: <lens> → <role>: <standing finding, one per lens> | plan: <path>
   ```
