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

### Architecture Compliance

- [ ] Architecture patterns from plan followed
- [ ] ADRs referenced in story were followed
- [ ] Security patterns applied (if Security Review = Yes in plan)
- [ ] **Platform Primitive compliance** — No new primitive bypasses without an annotated reason; if the project has `docs/architecture/BYPASS-REGISTER.md` and it grew, the PR description cites an ADR or justifies inline
- [ ] **Bypass register regenerated** — if any new `# *-BYPASS-OK:` annotation was added, the register was regenerated (`bash scripts/generate-bypass-register.sh --write`) and committed
- [ ] Not applicable → skip if no architecture constraints in plan

### Testing

- [ ] Test types from plan implemented (Unit/Integration/E2E)
- [ ] Coverage meets project thresholds
- [ ] Tests passing locally

### Post-Implementation Semantic Checks

Verify each item that applies. Skip items that don't apply to your change.

- [ ] **Database migrations tested locally** — Run migration tool locally, verify success
- [ ] **Migration idempotent** — DDL uses `IF NOT EXISTS`/`IF EXISTS`, data uses `ON CONFLICT DO NOTHING`
- [ ] **Timezone handling** — Date strings use local getters (not `toISOString().slice(0,10)` or UTC-only)
- [ ] **Range validation** — Date/Number ranges have `from > to` guards
- [ ] **State wiring complete** — New data fields flow through all layers: storage → service → API → UI
- [ ] **Index column order** — Selectivity left-to-right for composite indexes
- [ ] **String length validation** — Text/VARCHAR columns have length validation before insert
- [ ] **Test depth** — Tests verify actual behavior and parameters, not just return values
- [ ] **i18n complete** — All user-facing strings use translation functions (if project uses i18n)
- [ ] **Horizontal scalability** — No new process-local mutable state introduced (no new `TTLCache`, module-level mutable `dict`/`list`/`set`, `@lru_cache` on non-pure funcs, class-level mutable on singletons, `global` mutation, or in-process locks used for cross-request coordination). State that outlives a request lives in Postgres, Redis, or a queue. Exceptions carry an inline `# SCALABILITY-EXEMPT: <reason>` comment.
- [ ] **Not applicable** → skip if item does not apply (no migration/date/range/state/index/text column/i18n/scalability)

### Quality Gates

- [ ] `/we:review` passed (review_passed checkpoint)
- [ ] `/we:static` passed (static_analysis_passed checkpoint)
- [ ] `/we:test` passed (test_passed checkpoint)
- [ ] Local CodeRabbit passed (coderabbit_passed checkpoint — 0 BLOCKING findings)

### Documentation

- [ ] API changed → API docs/types regenerated
- [ ] Architecture changed → Architecture documentation updated
- [ ] CLI changed → CLI documentation updated
- [ ] Configuration changed → Configuration docs updated
- [ ] Documentation Impact from plan addressed (if specified)
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

## Review Output Format

Code reviewers (`/we:review`) should include in their output:

1. **AC Alignment Table** — Each AC individually checked with status and evidence
2. **DoD Quick Check** — Architecture compliance, security, wiring, test depth summary

---

## Quick Check

```
All ACs individually verified?
Feature reachable for user?
End-to-end flow works?
Architecture compliance? (patterns, ADRs, security)
Post-implementation semantic checks? (migrations, timezone, wiring, ...)
Quality gates passed? (review + static + test + coderabbit)
Docs updated? (per Documentation Impact in plan)
PR created and CI green?
All BLOCKING/WARNING fixed?
Ticket → In Review?

All yes → Story is DONE (awaiting user merge)
```
