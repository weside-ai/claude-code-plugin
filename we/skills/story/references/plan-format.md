# Story plan format

## Contents

Frontmatter · The refined scan · Lifecycle · Sections, in this order (Context, Open Fork, Acceptance
Criteria, User Journey, Testing Requirements, Verification, Technical Approach, Implementation
Phases, Out of scope, Constraints and Pins, Design Decisions, Code Guidance, Security Review
Required, Documentation Impact, Updates Log) · Oracle-class marker · Updates Log lines.

The contract between the writers (`/we:story`, `/we:refine`) and the readers (`/we:orchestrate`,
`/we:develop`). Change a field here only together with every reader.

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
| `status` | `draft` until the user approved, and while an `## Open Fork` stands; `approved` after. `built`, `done`, `merged`, `shipped` and `in review` count as built. |
| `comments_read_through` | Id or timestamp of the newest ticket comment the plan answers, or `none`. A newer comment means the plan may be stale. |
| `parallel_groups` | `[[2, 3]]` lets phases 2 and 3 run concurrently. Only for phases with disjoint `**Files:**` and a fixed contract between them; `[]` (serial) is the normal case. |
| `type`, `created` | Informational. |

## The refined scan

A plan counts as refined when all three hold:

1. The tokens `Given`, `When` and `Then` appear. The test is case-sensitive and file-wide, so it
   cannot catch one lowercase keyword in one AC: capitalise all three in every AC.
2. At least one line matches `^### Phase \d+`. Write `### Phase N: Title`, no leading zeros.
3. `## Context` carries more than 50 non-whitespace characters before the next level-2 header.

The scan cannot see an `## Open Fork` section. A plan carrying one is not dispatchable, and
every reader checks for it by hand.

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

Three lists here each cost review rounds when missing (Codex rounds, 10/2026):

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
- **Files:** <every file the change touches, including generated artifacts and the existing
  test files whose call sites break>
- **Risk:** <ordinary | migration | money | auth | tenant-isolation> — <on what; also name a
  promise that must hold across several code paths, a transaction or idempotency, or a fix
  routing around a fragile path, because the Lead picks `we:dev-high` from this line>
- **Approach:** <how>

## Out of scope

- <Work beyond the ticket's "done when": one named follow-up per line, with the reason it is
  outside. Never a phase; nobody files it during the run.>

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
`**Staging checks:**` names the file of checks the Tester runs on staging after the deploy
(`references/working-mode.md` § Roles). Its path, format, planned state and validate command are
the repo's, named in `.weside/verify.md`; each check carries the `id` of the AC it proves (`AC<n>`,
more than one per AC `AC<n>-b`), so the run's report maps back to the ACs. The refiner writes the
file next to the plan for every `receipt` AC, in the planned state, and runs the validate command;
plan and file land on the default branch in one commit (`references/plan-commit.md`). The builder
arms it in the build branch (drops the planned state) and may correct seed, fields and assertions
to the built code. Mechanical staging ACs (status code, field,
label) belong there; the prose ACs keep the new and fuzzy ones. A repo whose `.weside/verify.md`
names no staging checks writes `none — no staging checks in this repo`.

## Oracle-class marker

Every AC ends with its oracle class in brackets, backticks around the class tolerated: `[receipt]`
(a mechanical check in the repo's staging-check file), `[ci: <test>]` (a test in CI proves it) or
`[walk: <persona> · <screen>]` (a person walks it). A reader takes the marker only at the end of an
AC's full text, a wrapped AC included; a marker quoted mid-sentence is prose.

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
nobody measured is `absent`, never `0`. Only a session of its own is measured (`agents.worker_launch`
is a command template, `references/worker-dispatch.md` § Worker launch backend): a subagent shares
its caller's session id. The message the step sends after the line is not counted.
