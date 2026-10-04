# Story plan format

## Contents

Frontmatter · The refined scan · Lifecycle · Sections, in this order (Context, Open Fork, Acceptance
Criteria, User Journey, Testing Requirements, Verification, Technical Approach, Implementation
Phases, Out of scope, Constraints and Pins, Design Decisions, Code Guidance, Security Review
Required, Documentation Impact).

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

1. **Given** <state> **When** <action> **Then** <observable result>

## User Journey

1. <start> 2. <action> 3. <result> — the story is done when a user can walk it end to end.
<A purely technical story says so here.>

## Testing Requirements

- <Per AC, at the repo's `test_discipline` level: the runnable suite, the database, the phase.>

## Verification

- **Oracle:** <cli | ui | substitute | not-applicable — the highest rung the ACs demand, and why>
- **Seed:** <the command that puts the system into the state to observe>
- **Asserted:** <what must be true: endpoint + field, or route + label>
- **Not proven:** <what this oracle cannot show, and who owes it>
- **Exit criterion:** <what someone else could run to decide "done">
- **Missing CLI verb:** <a seed or assert the repo's CLI cannot do yet, and the phase that ships it>

## Technical Approach

<Patterns, primitives, the seam; the architecture refs used; how the `**Files:**` lists were
derived — code graph, or "grep-derived, no code graph".>

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
```

The four labels `**Oracle:**`, `**Seed:**`, `**Asserted:**` and `**Not proven:**` are copied into
the PR body, where a hook reads them literally: keep them undecorated.
