# Plan File Format — Cross-Skill Contract

Plan files at `docs/plans/{TICKET}-story.md` are the **build contract** between
`/we:story` (which writes them) and `/we:build` (which consumes them). This
document specifies the exact format both sides depend on. Changes here are
versioned and require explicit consideration of both sides.

> **Filename suffix:** story plans use the `-story.md` suffix. `/we:build`
> reads `docs/plans/{TICKET}-story.md` first and falls back to the legacy
> `{TICKET}-plan.md` so pre-existing plans keep building during migration. New plans
> are always written with `-story.md`.

---

## Frontmatter (YAML)

Every plan file begins with a YAML frontmatter block:

```yaml
---
story: {TICKET}         # Ticket key (e.g. PROJ-123). Required.
created: YYYY-MM-DD     # ISO date. Required.
status: draft           # One of: draft | approved. Required.
parallel_groups: []     # Optional. See § parallel_groups below.
---
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `story` | string | yes | Ticket key; used by `/we:build` for checkpoint keying |
| `created` | ISO-8601 date | yes | Informational; used in stale-plan detection |
| `status` | enum | yes | `draft` while being refined; `approved` after `/we:story` Step 5 |
| `parallel_groups` | list of lists | no | Empty or absent = all phases sequential; see below |

---

## Phase Headers

Phase headers follow the exact regex `^### Phase (\d+): (.+)$`:

```markdown
### Phase 1: Setup database schema
### Phase 2: Implement API endpoints
### Phase 3: Wire frontend
```

`/we:build` extracts phase numbers from capture group 1 (`\d+`) and phase
titles from capture group 2 (`.+`). **Do not deviate from this format** — no
leading zeros, no alternative numbering, no extra text before the phase number.

---

## Acceptance Criteria

Each AC uses Given/When/Then (GWT) structure:

```markdown
## Acceptance Criteria
1. **Given** [initial context] **When** [user action] **Then** [observable outcome]
2. **Given** [initial context] **When** [user action] **Then** [observable outcome]
```

The DoR (`we/quality/dor.md`) requires GWT structure. `/we:build` Step 1 scans
for the presence of `Given`, `When`, and `Then` tokens in the AC section — the
plan is rejected at the DoR gate if any are absent.

---

## Context Section

```markdown
## Context

[Informal brief — written as if explaining to a developer who just joined
the conversation. Capture: what problem we're solving and why NOW, what the
user cares about most, constraints that aren't obvious from the code, and
any important context from the design discussion. 3-8 sentences, narrative voice.]
```

`/we:build` Step 1 checks that the Context section is non-empty (> 50 characters).
A plan without meaningful context cannot be consumed reliably by an autonomous build.

---

## parallel_groups

`parallel_groups` is a list of lists of phase numbers. It signals to `/we:build`
Step 2 which phases can run as concurrent sub-agents:

```yaml
parallel_groups: []          # All phases sequential (default)
parallel_groups: [[2, 3]]    # Phases 2 and 3 run concurrently; everything else inline
parallel_groups: [[2, 3], [5, 6]]  # Two parallel groups
```

**Semantics:**

- A phase not mentioned in any group always runs inline in plan order.
- Phases within the same group are dispatched as concurrent sub-agents in a
  single `Agent()` message — they must touch **disjoint files** and have **no
  ordering dependency** (phase N's output must not feed phase N+1 within the group).
- Conflict detection after a parallel group returns is `/we:build`'s responsibility.
  If merge conflicts occur, the `parallel_groups` declaration was incorrect — resolve
  manually, and update the plan via `/we:story` to prevent future recurrence.
- When in doubt, leave the list empty. Explicit sequential runs are always correct;
  parallelism is an optimization hint, not a requirement.

---

## Required Sections (DoR gate)

`/we:build` Step 1 hard-stops if any of the following are missing or empty:

| Check | What is verified |
|---|---|
| AC section non-empty | Contains at least one `Given` + `When` + `Then` token |
| Context section non-empty | More than 50 characters of narrative text |
| At least one Phase header | Matches `^### Phase (\d+): (.+)$` |

Failure message: `"Plan at docs/plans/{TICKET}-story.md is incomplete: missing <ACs|Context|Phase>. Run /we:story {TICKET} to complete it before /we:build."`

---

## Full Template

```markdown
---
story: {TICKET}
created: YYYY-MM-DD
status: draft
parallel_groups: []
---

# Plan: [Story Title]

## Context

[3-8 sentence narrative brief]

## Acceptance Criteria
1. **Given** [context] **When** [action] **Then** [result]

## User Journey
1. [Starting point]
2. [Action]
3. [Result]

## Testing Requirements
- Unit tests for [X]
- Integration tests for [Y]

## Technical Approach
**Patterns:** [relevant patterns]

## Implementation Phases

### Phase 1: [Name]
- **Goal:** [achieved outcome]
- **Files:** [affected files]
- **Approach:** [how]

### Phase 2: [Name]
...

## Design Decisions

| Decision | Alternatives Considered | Why This |
|----------|------------------------|----------|

## Code Guidance
**DO:** [pattern to follow]
**DON'T:** [anti-pattern to avoid]

## Security Review Required
[Yes/No] — [reason]

## Documentation Impact
- [ ] API docs
- [ ] Architecture docs
- [ ] README/Setup
- [ ] User-facing docs
- [ ] No documentation changes needed
```

---

## References

- [`we/skills/story/SKILL.md`](../we/skills/story/SKILL.md) — plan writer (producer)
- [`we/skills/build/SKILL.md`](../we/skills/build/SKILL.md) — plan consumer
- [`we/quality/dor.md`](../we/quality/dor.md) — Definition of Ready (DoR gate)

---

## Concept Doc Format — Saga + Epic Mirror Block

The Saga (`docs/plans/<saga>-saga.md`) and Epic (`docs/plans/<saga>-<epic>-epic.md`) docs are not part of the Build contract above — `/we:build` never reads them. (Both are flat under `docs/plans/`, distinguished by filename suffix; the saga-slug prefix on epics groups them — `ls docs/plans/<saga>-*` shows a saga and all its epics.) They are written and updated by `/we:saga` and `/we:epic`, and they carry an auto-generated *mirror block* that reflects child items from the ticketing tool. The mirror is the contract between the Plan skill (writer + consumer of its own block) and the user (owner of all surrounding prose).

### Frontmatter

```yaml
---
saga: <saga-slug>             # Saga only
epic: <epic-slug>             # Epic only
vision: <parent-vision-slug>  # Saga only, optional
saga: <parent-saga-slug>      # Epic only
ticket: <TICKETING-KEY>       # Epic only, optional
created: YYYY-MM-DD           # both
updated: YYYY-MM-DD           # both — refreshed by Mirror-refresh + Refine
status: <enum>                # both
---
```

Status enums:
- Saga: `draft | active | landed | abandoned`
- Epic: `draft | in-progress | selected | backlog | done`

### Mirror block — marker convention

Both docs include a section (`## Sub-Epics` in the `-saga.md`, `## Stories` in the `-epic.md`) that contains a marker-enclosed table:

```markdown
## Sub-Epics

<!-- mirror:start (auto-generated; do not edit by hand — run /we:saga to refresh) -->

_Mirror of child Epics in the ticketing tool, refreshed YYYY-MM-DD._

| Key | Title | Status | Last activity | Notes |
|---|---|---|---|---|
| <KEY> | <Title> | Done | YYYY-MM-DD | <free-form> |

<!-- mirror:end -->
```

Rules:

| Rule | Why |
|---|---|
| Markers `<!-- mirror:start ... -->` / `<!-- mirror:end -->` are MANDATORY | Lets the skill replace the block without scanning prose |
| Everything between markers is owned by the skill | Overwritten on every Mirror-refresh and every Refine |
| Everything outside markers is owned by the user | Never touched by the skill |
| Saga columns: `Key, Title, Status, Last activity, Notes` | Five columns; Notes is free-form (blockers, links) |
| Epic columns: `Key, Title, Status, Plan, Last activity, Notes` | Six columns — `Plan` is `✓` if `docs/plans/{KEY}-story.md` exists (legacy `{KEY}-plan.md` also counts), `—` otherwise |
| Status vocabulary normalised | Saga: Done / Active / Backlog / Blocked. Epic: Done / Active / Refined / Backlog / Blocked |
| Refresh updates only the mirror block, `updated:` field, and Updates Log | Lightweight, no plan-mode, no user prose touched |

### Updates Log

Both docs carry an `## Updates Log` section appended to (never rewritten by) the skill:

```markdown
## Updates Log

- 2026-05-14 — created
- 2026-05-22 — mirror refresh (10 child epics; +1 added, −0 removed, !2 status-changed)
- 2026-05-27 — refined via /we:saga
```

### Drift detection (read-only, run on every Status)

The Status mode compares the mirror block in the doc with the live ticketing fetch and surfaces:

- Children in ticketing not in the mirror (`+`)
- Mirror entries that no longer exist in ticketing (`−`)
- Status mismatches between mirror and ticketing (`!`)
- Epic-specific: children marked Active in ticketing without a refined plan on disk (`⚠`)
- Free-form notes the skill picked up from the prose (`•`) — e.g. a hypothesis marked falsified while frontmatter still reads draft, a sequencing phase referenced as next that is already Done

### Concept Doc References

- [`we/skills/saga/SKILL.md`](../we/skills/saga/SKILL.md) — Saga writer + consumer
- [`we/skills/epic/SKILL.md`](../we/skills/epic/SKILL.md) — Epic writer + consumer
- [`we/skills/coach/SKILL.md`](../we/skills/coach/SKILL.md) — surfaces a one-line Plan-status from the mirror

---

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-05-18 | Initial spec extracted from `/we:story` + `/we:build` implementation |
| 1.1 | 2026-05-28 | Concept Doc Format section added — Saga + Epic mirror block contract (v2.34.0) |
