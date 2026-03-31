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

### Recommended

- [ ] **Dependencies** — Blockers identified
- [ ] **Risks Identified** — Technical unknowns, spike needed?
- [ ] **Complexity Estimated** — S/M/L

### Vision Alignment (optional)

If `.weside/vision.md` exists in the project, verify the story aligns with project vision.
If a weside Companion is connected, check story against Companion Goals.

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
