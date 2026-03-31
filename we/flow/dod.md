# Definition of Done (DoD)

**A story is DONE when all criteria below are met.**

---

## Checklist

### Code Quality

- [ ] Code implemented and functional
- [ ] Acceptance Criteria individually verified (each AC checked with evidence)
- [ ] Feature REACHABLE: User can navigate to the feature (button/route/screen)
- [ ] End-to-end: Complete user flow works, not just individual parts
- [ ] No unresolved TODO/FIXME left

### Testing

- [ ] Test types from plan implemented (Unit/Integration/E2E)
- [ ] Coverage meets project thresholds
- [ ] Tests passing locally

### Quality Gates

- [ ] `/we:review` passed (review_passed checkpoint)
- [ ] `/we:static` passed (static_analysis_passed checkpoint)
- [ ] `/we:test` passed (test_passed checkpoint)

### Documentation

- [ ] API changed → Types/docs regenerated
- [ ] Architecture changed → Docs updated
- [ ] No doc changes needed (skip if nothing relevant changed)

### CI/CD

- [ ] PR created (pr_created checkpoint)
- [ ] CI passed or reviews green
- [ ] All BLOCKING/WARNING issues fixed

### Ticketing

- [ ] Ticket moved to "In Review"
- [ ] User reviewed and merged
- [ ] Ticket moved to "Done" — **USER ONLY, never automated**

---

## Issue Severity

| Level | Action |
|---|---|
| **BLOCKING** | MUST fix |
| **WARNING** | MUST fix |
| **INFO/NITPICK** | Fix or document skip reason |

---

## Quick Check

```
All ACs individually verified?
Feature reachable for user?
End-to-end flow works?
Quality gates passed? (review + static + test)
Docs updated?
PR created and CI green?
All BLOCKING/WARNING fixed?
Ticket → In Review?

All yes → Story is DONE (awaiting user merge)
```
