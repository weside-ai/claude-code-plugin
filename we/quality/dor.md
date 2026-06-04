# Definition of Ready (DoR)

**A story is READY for development when all criteria below are met.**

---

## Checklist

### Required (Blocking)

- [ ] **Clear Summary** — One-line description (max 80 chars)
- [ ] **User Story** — "As [role] I want [feature] so that [benefit]" format
- [ ] **Plan exists** — `docs/plans/{TICKET}-story.md` with implementation details. Once the plan is final, `/we:build` executes it without re-negotiating scope, phasing, or PR size — open questions belong in `/we:story`, not in the pipeline. For stories with 3+ independent phases (disjoint files, no ordering dependency), the plan frontmatter optionally declares `parallel_groups` (list-of-lists of phase numbers) to enable parallel sub-agent dispatch in Step 2.
- [ ] **Ticket linked** — Connected to parent Epic (if using ticketing tool)

### In Plan (Details)

- [ ] **Context** — Narrative brief: why this story, what the user cares about, non-obvious constraints. Written so the implementing agent understands the intent, not just the spec.
- [ ] **Acceptance Criteria** — Testable, Given/When/Then format
- [ ] **User Journey** — End-to-end steps from user's perspective (skip for purely technical stories)
- [ ] **Design Decisions** — Alternatives considered during refinement and why they were rejected
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
| User Story | Ticket (minimal) | `/we:story` |
| **Implementation Plan** | `docs/plans/{TICKET}-story.md` | `/we:story` |
| → Context | Plan | (in /we:story) |
| → Acceptance Criteria | Plan | (in /we:story) |
| → User Journey | Plan | (in /we:story) |
| → Design Decisions | Plan | (in /we:story) |
| → Testing Requirements | Plan | (in /we:story) |
| → Technical Approach | Plan | (in /we:story) |
| → Security Review | Plan | (in /we:story) |
| → Documentation Impact | Plan | (in /we:story) |

**`/we:story` creates Ticket + Plan in one step.**

---

## Ticket Template (Minimal)

```markdown
## User Story

As [role] I want [feature] so that [benefit].

## Plan

Implementation Plan: docs/plans/{TICKET}-story.md
```

**Details are in the Plan, NOT in the ticket.**

---

## Quick Check

```
User Story in ticket?
Plan exists? (docs/plans/{TICKET}-story.md)
Context section written? (in plan — why this story, what matters)
ACs defined? (in plan, Given/When/Then)
Design Decisions documented? (in plan — alternatives + reasoning)
Documentation impact identified? (in plan)

All yes → Story is READY
Any missing → Run /we:story first
```

---

## Backwards Compatibility

| Story Type | Status |
|-----------|--------|
| With Plan file | Ready |
| With inline Implementation Notes | Acceptable (legacy) |
| Without anything | Not Ready → `/we:story` |

---

## Checkpoint

After `/we:story`: `phase=refined`

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint {TICKET} refined
```
