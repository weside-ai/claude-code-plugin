# Definition of Ready (DoR)

**A story is READY for development when all criteria below are met.**

A repo can extend this checklist with its own criteria in `.weside/dor.md` (created by `/we:setup`); `/we:story` and `/we:orchestrate` read it additively — both the checklist below and the repo file apply, the repo file never replaces this one.

---

## Checklist

### Required (Blocking)

- [ ] **Clear Summary** — One-line description (max 80 chars)
- [ ] **User Story** — "As [role] I want [feature] so that [benefit]" format
- [ ] **Plan exists** — `docs/plans/{TICKET}-story.md` with implementation details. Once the plan is final, the pipeline executes it without re-negotiating scope, phasing, or PR size — open questions belong in `/we:story`, not in the build. For stories with 3+ independent phases (disjoint files, no ordering dependency), the plan frontmatter optionally declares `parallel_groups` (list-of-lists of phase numbers), the parallel-wave map `/we:orchestrate` dispatches from.
- [ ] **Ticket linked** — Connected to parent Epic (if using ticketing tool)

### In Plan (Details)

- [ ] **Context** — Narrative brief: why this story, what the user cares about, non-obvious constraints. Written so the implementing agent understands the intent, not just the spec.
- [ ] **Acceptance Criteria** — Testable, Given/When/Then format
- [ ] **User Journey** — End-to-end steps from user's perspective (skip for purely technical stories)
- [ ] **Design Decisions** — Alternatives considered during refinement and why they were rejected
- [ ] **Testing Requirements** — Which test types (Unit/Integration/E2E)? Edge cases?
- [ ] **Technical Approach** — Layers, patterns, relevant architecture decisions
- [ ] **Glossary vocabulary** — Terms match the repo-root `CONTEXT.md` glossary, if one exists (no `_Avoid_` terms)
- [ ] **Security Review Required** — Yes/No with reason
- [ ] **Code Guidance** — DO/DON'T patterns for implementation
- [ ] **Documentation Impact** — Where does the knowledge land? Answer along the DoD cascade (`quality/dod.md` § Documentation): a docstring at the site, the one thematic architecture doc, or an ADR. **"Nowhere — the code carries it" is a complete answer**, and the usual one. Naming a NEW doc means saying why the code cannot hold it. Read by `/we:docs` in pipeline Step 6.

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

`/we:story` writes both, in one step: the **ticket** (minimal — the user story plus a link) and the
**plan** at `docs/plans/{TICKET}-story.md`, which carries every section listed above.

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

A story missing any Required or In-Plan item is **not READY** — run `/we:story` first. A legacy
story carrying inline Implementation Notes instead of a plan file is acceptable; one carrying
neither is not.

The machine-checkable subset of this checklist (GWT ACs · Context · Phase headers) is the 3-item
scan in `references/dor-scan.md` — that is what the pipeline gates on before dispatching.

---

## Checkpoint

After `/we:story`: `phase=refined`

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint {TICKET} refined
```
