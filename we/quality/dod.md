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
- [ ] Coverage meets project thresholds (verified by CI on push — not a local gate)
- [ ] **Affected tests pass locally** — tests covering the diff (mapped paths for pytest, `--findRelatedTests` for Jest); the full suite runs in CI. Fall back to the full local suite when the diff touches `conftest.py`, jest config, fixtures, or >50 files.

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
- [ ] **Cross-request ORM cache safety** — Any cache that holds SQLAlchemy ORM objects across request/session boundaries (e.g. `ReferenceDataService`) MUST eager-load every relationship it serves and detach the row from its loading session. Lazy attributes on a cached row crash the next request with `DetachedInstanceError`. CRUD reads feeding such a cache use `selectinload(...)` for every relationship downstream code touches; the cache calls `session.expunge(row)` before storing. Caught live on WA-984: `preset.llm_model.*` after the second chat call.
- [ ] **New reference table classification** — A new table that is static/global (same for every tenant, seeded via Alembic) AND read on a hot path (per LLM call / request / turn) belongs to the `config_*` family: name it `config_<name>` and add a typed accessor on `ReferenceDataService`. Direct CRUD reads on the hot path bypass the 5-min cache and re-introduce per-call DB load. Tenant-scoped tables (RLS, runtime writes) keep the unprefixed name. KV strings live in `system_config` + `ConfigService`.
- [ ] **Not applicable** → skip if item does not apply (no migration/date/range/state/index/text column/i18n/scalability)

### Quality Gates

- [ ] `/we:review` passed (review_passed checkpoint)
- [ ] `/we:static` passed (static_analysis_passed checkpoint)
- [ ] `/we:test` passed (test_passed checkpoint)
- [ ] CodeRabbit threads resolved on GitHub — `check-coderabbit` CI gate blocks on unresolved CRITICAL/MAJOR threads. Use `/we:ci-review` to fix and resolve after PR creation.

### Documentation

- [ ] API changed → API docs/types regenerated
- [ ] Architecture changed → Architecture documentation updated
- [ ] CLI changed → CLI documentation updated
- [ ] Configuration changed → Configuration docs updated
- [ ] User-flow changed → Journey doc updated or created (`docs/architecture/journey-*.md`)
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
Quality gates passed? (review + static + test locally, CodeRabbit on GitHub)
Docs updated? (per Documentation Impact in plan)
PR created and CI green?
All BLOCKING/WARNING fixed?
Ticket → In Review?

All yes → Story is DONE (awaiting user merge)
```
