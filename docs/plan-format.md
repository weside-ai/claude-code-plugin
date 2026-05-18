# Plan File Format — Cross-Skill Contract

Plan files at `docs/plans/{TICKET}-plan.md` are the **build contract** between
`/we:story` (which writes them) and `/we:build` (which consumes them). This
document specifies the exact format both sides depend on. Changes here are
versioned and require explicit consideration of both sides.

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

Failure message: `"Plan at docs/plans/{TICKET}-plan.md is incomplete: missing <ACs|Context|Phase>. Run /we:story {TICKET} to complete it before /we:build."`

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

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-05-18 | Initial spec extracted from `/we:story` + `/we:build` implementation |
