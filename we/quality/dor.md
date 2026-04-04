# Definition of Ready (DoR)

**A story is READY for development when all criteria below are met.**

---

## Checklist

### Required (Blocking)

- [ ] **Clear Summary** — One-line description (max 80 chars)
- [ ] **User Story** — "As [role] I want [feature] so that [benefit]" format
- [ ] **Plan exists** — `docs/plans/{TICKET}-plan.md` with implementation details
- [ ] **Ticket linked** — Connected to parent Epic (if using ticketing tool)

### In Plan (Details)

- [ ] **Acceptance Criteria** — Testable, Given/When/Then format
- [ ] **Testing Requirements** — Which test types (Unit/Integration/E2E)? Edge cases?
- [ ] **Technical Approach** — Layers, patterns, relevant architecture decisions
- [ ] **Security Review Required** — Yes/No with reason
- [ ] **Code Guidance** — DO/DON'T patterns for implementation
- [ ] **Documentation Impact** — Which docs are affected? (API, architecture, README, user-facing). Used by `/we:docs` in pipeline Step 6.

### Recommended

- [ ] **Dependencies** — Blockers identified
- [ ] **Risks Identified** — Technical unknowns, spike needed?
- [ ] **Complexity Estimated** — S/M/L

### Vision Alignment (optional)

If `.weside/vision.md` exists in the project:
1. Read the vision document
2. For each dimension defined in the vision, ask: **Does this story advance this dimension?**
3. If the vision uses custom dimensions, apply those. If no dimensions are defined, check general alignment.
4. Story should align with at least the majority of relevant dimensions.

If a weside Companion is connected, check story against Companion Goals automatically.

If no vision exists: skip this check entirely.

---

## Auto-Reject Patterns

Stories with these patterns are **NOT READY** — send back for refinement:

| Pattern | Why it blocks |
|---------|--------------|
| No acceptance criteria | Not testable — how do you verify it works? |
| No plan | WHY and HOW are unknown — development will stall |
| No user story | No user value articulated — why are we building this? |
| Contradicts documented vision | Feature works against the project's stated goals |
| No clear entry point | User can't reach the feature — "reachable" must be plannable |

---

## Who Writes What?

| Section | Where | Command |
|---------|-------|---------|
| User Story | Ticket (minimal) | `/we:refine` |
| **Implementation Plan** | `docs/plans/{TICKET}-plan.md` | `/we:refine` |
| → Acceptance Criteria | Plan | (in /we:refine) |
| → Testing Requirements | Plan | (in /we:refine) |
| → Technical Approach | Plan | (in /we:refine) |
| → Security Review | Plan | (in /we:refine) |
| → Documentation Impact | Plan | (in /we:refine) |

**`/we:refine` creates Ticket + Plan in one step.**

---

## Ticket Template (Minimal)

```markdown
## User Story

As [role] I want [feature] so that [benefit].

## Plan

Implementation Plan: docs/plans/{TICKET}-plan.md
```

**Details are in the Plan, NOT in the ticket.**

---

## Quick Check

```
User Story in ticket?
Plan exists? (docs/plans/{TICKET}-plan.md)
ACs defined? (in plan, Given/When/Then)
Documentation impact identified? (in plan)

All yes → Story is READY
Any missing → Run /we:refine first
```

---

## Backwards Compatibility

| Story Type | Status |
|-----------|--------|
| With Plan file | Ready |
| With inline Implementation Notes | Acceptable (legacy) |
| Without anything | Not Ready → `/we:refine` |

---

## Checkpoint

After `/we:refine`: `phase=refined`

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint {TICKET} refined
```
