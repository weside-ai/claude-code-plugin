# Story plan format

## Contents

Frontmatter · Readiness · Lifecycle · Sections, in this order (Context, Open Fork, Acceptance
Criteria, User Journey, Testing Requirements, Verification, Technical Approach, Implementation
Phases, Out of scope, Constraints and Pins, Design Decisions, Code Guidance, Security Review
Required, Documentation Impact, Updates Log) · Oracle-class marker · What the Ready gate reads ·
Updates Log lines.

The contract between the writer (`/we:plan-story`, run by a refiner worker the epic's master starts) and the readers (`/we:master`,
`/we:develop`, `scripts/ready_gate.py`). This file owns the grammar the gate parses; change a field
here only together with every reader.

The file is `docs/plans/{TICKET}-story.md`. `{TICKET}` is the Jira key, the bare GitHub issue
number, or a kebab-case slug when there is no ticketing tool. The same token names the file, the
`story:` field and the branch.

## Frontmatter

Every line is a bare `key: value`, lists inline as `[a, b]`, no trailing `# comment`: a reader
takes the rest of the line as the value.

```yaml
---
type: story-plan
story: {TICKET}
epic: {EPIC-SLUG-OR-KEY}
depends_on: []
comments_read_through: none
created: YYYY-MM-DD
status: draft
parallel_groups: []
---
```

| Key | What readers do with it |
|---|---|
| `story` | Roster and branch key; the file name is the fallback. |
| `epic` | An epic run rosters by it; without it the story is invisible there. Omit the line only for a standalone story. |
| `depends_on` | Keys that must be built before this story is dispatched. |
| `status` | `draft` while an `## Open Fork` stands or the Ready gate fails; `approved` once the DoR scan and the claim check pass: the master sets it in the commit that puts the plan on the default branch (`/we:master` § Refine lane); `/we:plan-story` writes `draft`. The `/flow` pane and the `/board` work tree read it for the Approval lamp; Selected itself comes from `board.py select`. Approval is per epic (L0 §Units), never per story; the one exception is the master card's fence rule. `built`, `done`, `merged`, `shipped` and `in review` count as built. |
| `comments_read_through` | Id or timestamp of the newest ticket comment the plan answers, or `none`. A newer comment means the plan may be stale. |
| `parallel_groups` | `[[2, 3]]` lets phases 2 and 3 run concurrently. Only for phases with disjoint `**Files:**` and a fixed contract between them; `[]` (serial) is the normal case. |
| `type`, `created` | Informational. |

## Readiness

A plan is ready when `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ready_gate.py story <plan>` exits 0;
it prints one line per gap (§ What the Ready gate reads). A plan carrying `## Open Fork` is never
ready. An epic plan is checked with `ready_gate.py epic <epic plan>`.

## Lifecycle

Before the PR merges, the builder records in the plan only where the build deviated from it; the
next agent reads the plan, not the diff.

## Sections, in this order

```markdown
# Plan: <Story title>

## Context

<Narrative brief, 3–8 sentences, no bullets: the problem, why now, what the user cares
about most, constraints the code does not show, what the discussion settled. The
implementing agent leans on this section more than on any other.>

## Open Fork

<Only when a refiner hit a fork nothing settles, directly after Context: the question in
one line, option A and option B with their consequences, the recommendation and why.
Answering the fork deletes the section.>

## Acceptance Criteria

1. **Given** <state> **When** <action> **Then** <observable result> [<oracle class>]

## User Journey

1. <start> 2. <action> 3. <result> — the story is done when a user can walk it end to end.
<A purely technical story says so here.>

## Testing Requirements

- <Per AC, at the repo's `test_discipline` level: the runnable suite, the database, the phase.>

## Verification

- **Oracle:** <cli | ui | substitute | not-applicable | not-observed — the highest rung the ACs demand, and why>
- **Seed:** <the command that puts the system into the state to observe>
- **Asserted:** <what must be true: endpoint + field, or route + label>
- **Not proven:** <what this oracle cannot show, and who owes it>
- **Exit criterion:** <what someone else could run to decide "done">
- **Staging checks:** <the staging-check file `.weside/verify.md` names, one check per AC, each with that AC's `id` | none — why>
- **Missing CLI verb:** <a seed or assert the repo's CLI cannot do yet, and the phase that ships it>

## Technical Approach

<Patterns, primitives, the seam; the architecture refs used; how the `**Files:**` lists were
derived — code graph, or "grep-derived, no code graph".>

Three lists here each cost review rounds when missing:

- **Writes into two systems** (a table and an API, a table and a cache, two transactions): every outcome
  combination — both succeed, the first fails, the second fails, a timeout after the first — and what the
  code does in each.
- **Foreign markup** the change parses or emits (Markdown, HTML, a platform's markup): its input forms up
  front — nested, escaped, empty, unterminated, the platform's own variants.
- **Error arms** on the changed path, including every broad catch (`except Exception`, a bare `except`,
  `catch (e)`) and what it swallows.

## Implementation Phases

### Phase 1: <Title>

- **Goal:** <the outcome>
- **Repo:** <only when the phase works in another repo: its name, as the epic's `fence:` writes it>
- **Files:** <every file the change touches, including generated artifacts and the existing
  test files whose call sites break>
- **Risk:** <ordinary | migration | money | auth | tenant-isolation> — <on what; also name a
  promise that must hold across several code paths, a transaction or idempotency, or a fix
  routing around a fragile path, because the Lead picks `we:dev-high` from this line>
- **Test first:** <only with `test_discipline: tdd`: the test written first, its suite and the CI job
  that runs it>
- **Approach:** <how; in a phase with a `**Repo:**` line: the target and its check (which paths must
  pass, which must not), never a code line quoted from that repo: its owner writes it at build time,
  and a quoted line goes stale before the build>

## Out of scope

- <Work beyond the ticket's "done when": one named follow-up per line, with the reason it is
  outside. Never a phase; nobody files it during the run. New visible behaviour goes to the epic's
  `## Extensions` instead (`references/epic-plan.md` § Finish line), not into this plan.>

A story that corrects a kind of statement (claims, wording, copy across repos) lists every site in
`## Context` before the Ready gate, from one search over all repos and languages; its done-when is
that list. A site found after Ready is an Extensions entry, never a "part N" of this story; a defect
at a listed site is fixed in the story.

| Correction plan | Verdict |
|---|---|
| `## Context`: "42 sites: landing 18, app 11, backend 7, docs 6 (search: `rg -i 'always\|never' …` over 4 repos)" | good: closed list, the search named |
| `## Context`: "fix the absolute claims in the FAQ and wherever else we find them" | bad: no end, every round finds the next site |

## Constraints and Pins

**Constraints:** <conventions and primitives the change composes>
**Pins:** <existing behaviour that must not change, precise enough to conflict against>
**<Repo DoR row name>:** <one labelled line per row of `.weside/dor.md`; the Lead gates by name>

## Design Decisions

| Decision | Alternatives considered | Why this, decided by whom |
|---|---|---|

## Code Guidance

**DO:** <pattern> · **DON'T:** <anti-pattern>

## Security Review Required

<Yes | No> — <reason; Yes (money, auth, tenant isolation, migration) means the finish runs `code-review` at `high` on the diff>

## Documentation Impact

- **Docstrings** — <which symbols carry the reasoning; the default answer>
- **Architecture doc** — <only when the interplay across modules changes>
- **ADR** — <only when hard to reverse, surprising and a real trade-off>
- **Generated** — <API spec, clients, CLI reference to regenerate>
- **New doc** — <only with the reason the code cannot hold it>

## Updates Log

- <one line per measured step, appended by a script; grammar below>
```

The block is copied into the PR body, where a hook reads the `**Oracle:**` line literally: keep it
undecorated. It must pick one value; `not-applicable` (no runtime behaviour) and `not-observed`
(behaviour not observed, e.g. unit tests only) each need their reason. `**Seed:**`, `**Asserted:**`
and `**Not proven:**` are what a reviewer needs to repeat the run; the hook does not check them.
`**Staging checks:**` names the file of checks the acceptance owner runs on staging after the deploy
(L0 §Sessions, the acceptance role). Its path, format, planned state and validate command are
the repo's, named in `.weside/verify.md`; each check carries the `id` of the AC it proves (`AC<n>`,
more than one per AC `AC<n>-b`), so the run's report maps back to the ACs. The refiner writes the
file next to the plan for every `receipt` AC, in the planned state, and runs the validate command;
plan and file land on the default branch in one commit, by the repo's docs path (`references/plan-commit.md`). The builder
arms it in the build branch (drops the planned state) and may correct seed, fields and assertions
to the built code. Mechanical staging ACs (status code, field,
label) belong there; the prose ACs keep the new and fuzzy ones. A repo whose `.weside/verify.md`
names no staging checks writes `none — no staging checks in this repo`.

## Oracle-class marker

Every AC ends with its oracle class in brackets: `[receipt]` (a mechanical check in the repo's
staging-check file), `[ci: <test>]` (a test in CI proves it) or `[walk: <persona> · <screen>]` (a
person walks it). This section owns the syntax only, not when to choose a class.

Syntax (an AC is a numbered item of `## Acceptance Criteria` and runs to the next item or header,
nested bullets and wrapped lines included):

- The marker is the last balanced `[...]` at the very end of the AC's text; brackets inside a
  backtick span do not count (`` `[[mock:call …]]` `` inside a marker is text). A marker quoted
  mid-sentence is prose.
- Its body splits on top-level `;` into parts. A part starts with a class token `receipt`, `ci` or
  `walk` (backticks around it tolerated) followed by `:`, whitespace or the end; the rest is its
  detail. The first part must start with one; a later part that starts with no class token
  continues the detail before it (`[ci: test_x.py; staging cannot see it]`). Any other token in
  that place is an unknown class.
- `ci` needs a detail: the test, and why staging cannot see it.
- `walk` needs a detail whose `·`-separated fields hold the persona and the screen; a field
  `why: <sentence>` says why a person walks a change outside the walk paths.
- `receipt` may say `boundary` (a server-boundary AC, judged against the mock-bound persona) or
  `not-boundary: <why>` (exempt from the boundary terms).
- Several classes in one marker: ``[`ci` for the file; `walk`: owner · settings]``.

### Two vocabularies named oracle

The AC marker and the Verification block's `**Oracle:**` line answer different questions; neither
word list maps onto the other.

| | AC marker (Ready gate) | `**Oracle:**` line (Verification block, PR hook) |
|---|---|---|
| Words | `receipt` · `ci` · `walk` | `cli` · `ui` · `substitute` · `not-applicable` · `not-observed` |
| Answers | who/what accepts the AC after merge | how the builder observed the change before the PR |
| Checked by | `ready_gate.py` (Ready) | `hooks/verification_gate.py` (PR body) |

An AC class on the `**Oracle:**` line (`**Oracle:** ci`) is refused by the PR hook; a `ci` AC is
still observed via `cli` or `not-observed`. The Ready gate warns on it early (§ What the Ready
gate reads, check 9).

## What the Ready gate reads

`ready_gate.py story <plan>` prints one line per failure, `<plan>: <place>: <what is missing>`, and
exits 1; exit 0 is ready, 2 a usage error. Warnings go to stderr, prefixed `warning:`, and never
change the exit. The gate takes the mode and the plan, nothing else: no option turns a check off.
Every repo value comes from the crew (`scripts/crew.py`).

Story checks, each failure one line, the run never stops at the first:

1. Frontmatter `story:` present; without `epic:` the fence and goal checks warn (§ Warn until present).
2. Every section of § Sections present except `## Code Guidance` and `## Updates Log`; an
   `## Open Fork` fails.
3. Every AC holds `**Given**`, `**When**`, `**Then**` and a marker.
4. Every marker parses (§ Oracle-class marker).
5. A `walk` part without `why:` passes only when a `**Files:**` path of a phase without
   `**Repo:**` matches a glob of the crew's `oracles.walk_paths`.
6. With a `receipt` AC the gate runs the crew's `oracles.receipt_check` (§ Receipt check).
7. A `receipt` AC is a boundary AC when its marker says `boundary` or its text matches a term of
   `acceptance.boundary_terms` (case-insensitive, whole words), unless the marker says
   `not-boundary: <why>`; boundary ACs need `acceptance.mock_persona`.
8. Fence, goal file and `serves:` (below), through the story's epic plan.
9. The `## Verification` block's `**Oracle:**` line, read by the PR hook's parser: a line the hook
   would refuse at `gh pr create` (an AC class such as `ci` there, a decline without reason) is one
   warning, never a failure.

**Files.** Under each `### Phase <n>:`, the bullets after `**Files:**` up to the next
`- **<Label>:**` bullet. A backtick span is a path when it holds no whitespace and contains `/`,
starts with `.`, or is a bullet's first span and ends in an extension; a trailing `:<line>[-<line>]`
is dropped. A phase line `- **Repo:** <name>` puts its paths in repo `<name>`; without it they are
the plan's repo, and a path marked `(other repo)` there fails until the phase names its repo.

**Epic plan.** The `*-epic.md` in the story plan's directory whose frontmatter `ticket:` or `epic:`
equals the story's `epic:`, or whose `linked_epics:` holds it; none warns (§ Warn until present), more than one fails. Its
frontmatter fields the gate reads:

- `fence: [<glob>, <repo>:<glob>, …]` — where the epic's stories may write. A bare glob covers the
  plan's repo, `<repo>:` another repo by its `**Repo:**` name. `**` matches any depth, `*` within
  one segment, `?` one character (the same matcher serves `walk_paths`). A path outside it is a
  `scope change` line naming the approver (`roles.product`, and `human.name` if it changes the
  outcome); approval is widening `fence:` on the default branch, the epic file is the record.
- `serves: <metric part>; <metric part>` — each part starts (casefolded, whitespace collapsed)
  with a metric name of the goal file, followed by the end, a space or `(`.

**Goal file** (crew `files.goals`): metrics are list items `- metric: <name>`, optionally followed
by an em dash and a definition; anything else is prose. A line naming a ticket key (crew `naming.key`) or
linking a target ending `-epic.md` or `-story.md` fails: the goal file names outcomes, not work.

**Warn until present.** An epic plan without `fence:` turns the fence check off, a crew without
`files.goals` the goal and `serves:` checks, an epic plan without `serves:` the `serves:` check:
each prints one `warning:` naming the reason and the backfill, and refuses nothing for it. The
check arms itself the moment its source lands, with no flag. A `files.goals` naming an absent file
is a crew error and refuses.

**Receipt check.** `oracles.receipt_check` is a command line; the gate runs it with the plan's path
appended, plus `--boundary-acs <n,…> --mock-persona <persona>` when boundary ACs exist, in the
crew's repo root, 60 s at most. Its stdout lines prefixed `warning:` go to stderr; every other line
is a failure; exit 1 without a line is one failure. A receipt AC with no command set fails.

`ready_gate.py epic <epic plan>` runs the `serves:`, goal-file and fence-presence parts and the finish
line (`references/epic-plan.md` § Finish line).

## Updates Log lines

`## Updates Log` is the plan's last section, created by the first line written into it. A step that
measures its token use appends one line through `${CLAUDE_PLUGIN_ROOT}/scripts/session_tokens.py --plan <plan> --step
<step>`, never by hand:

```text
- 2026-11-03 refine tokens: in=12 out=34567 cache_read=1234567 cache_write=23456 models=<model> session=fbae4d4e
- 2026-11-03 refine tokens: absent (subagent: no own session id)
```

`<date> <step> tokens:` then either the four counts (input, output, cache read, cache write),
followed by optional `key=value` pairs (`models`, `session` as the first eight characters,
`skipped` = unreadable transcript lines), or `absent (<reason>)` with no `)` in the reason. A value
nobody measured is `absent`, never `0`. Only a session of its own is measured (the worker template, `references/worker-dispatch.md` § Worker launch backend): a subagent shares
its caller's session id. The message the step sends after the line is not counted.
