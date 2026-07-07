# Definition of Done (DoD)

**A story is DONE when all criteria below are met.**

A repo can extend this checklist with its own criteria in `.weside/dod.md` (created by `/we:setup`); the `code-reviewer` agent reads it additively — both the checklist below and the repo file apply, the repo file never replaces this one.

---

## Checklist

### Code Quality

- [ ] Code implemented and functional
- [ ] Acceptance Criteria individually verified (each AC checked with evidence)
- [ ] Feature REACHABLE: User can navigate to the feature (button/route/screen)
- [ ] End-to-end: Complete user flow works, not just individual parts
- [ ] No unresolved TODO/FIXME left
- [ ] **Parallelisation considered** — for stories with 3+ independent implementation phases: `parallel_groups` is set in the plan frontmatter, or there is an explicit note in the plan explaining why phases must be sequential. Skip for stories with 1–2 phases.

### Architecture Compliance

- [ ] Architecture patterns from plan followed
- [ ] ADRs referenced in story were followed
- [ ] Security patterns applied (if Security Review = Yes in plan)
- [ ] **Platform Primitive compliance** — No new primitive bypasses without an annotated reason; if the project has `docs/architecture/BYPASS-REGISTER.md` and it grew, the PR description cites an ADR or justifies inline
- [ ] **Bypass register regenerated** — if any new `# *-BYPASS-OK:` annotation was added AND `scripts/generate-bypass-register.sh` exists in the repo, the register was regenerated (`bash scripts/generate-bypass-register.sh --write`) and committed; skip silently if the script is absent
- [ ] Not applicable → skip if no architecture constraints in plan

### Testing

- [ ] Test types from plan implemented (Unit/Integration/E2E)
- [ ] Coverage meets project thresholds (verified by CI on push — not a local gate)
- [ ] **Affected tests pass locally** — tests covering the diff (mapped paths for pytest, `--findRelatedTests` for Jest); the full suite runs in CI. Fall back to the full local suite when the diff touches `conftest.py`, jest config, fixtures, or >50 files.
- [ ] **Test quality per `references/test-discipline.md`** — no implementation-coupled tests, no tautological assertions, mocks at system boundaries only. Applies at every `test_discipline` level (the level only decides *when* tests are written).

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
- [ ] **Cross-request ORM cache safety** — Any cache that holds ORM objects across request/session boundaries MUST eager-load every relationship it serves and detach the row from its loading session. Lazy attributes on a cached row crash the next request with a "detached instance" error. Reads feeding such a cache use eager-load helpers (e.g. `selectinload`) for every relationship downstream code touches; the cache detaches the row before storing.
- [ ] **New reference table classification** — A new table that is static/global (same for every tenant, seeded via migration) AND read on a hot path (per LLM call / request / turn) belongs to a typed reference-data layer with a process-level cache. Direct CRUD reads on the hot path bypass the cache and re-introduce per-call DB load. Tenant-scoped tables (RLS, runtime writes) stay under the regular CRUD layer.
- [ ] **Not applicable** → skip if item does not apply (no migration/date/range/state/index/text column/i18n/scalability)

### Verification

- [ ] **Success claims require evidence** — "tests pass", "it works", "fixed" are assertions, not verification. Each claim must be backed by a pasted command + its actual output (in the PR description, a commit message, or an inline comment). An assertion without output fails this gate.

### Quality Gates

- [ ] `/we:review` passed (review_passed checkpoint)
- [ ] `/we:static` passed (static_analysis_passed checkpoint)
- [ ] `/we:test` passed (test_passed checkpoint)
- [ ] AI-reviewer threads resolved on GitHub — the repo's configured review gate(s) block on unresolved BLOCKING/WARNING (Critical/Major) threads. Use `/we:ci-review` to fix and resolve all bot threads after PR creation. Skip if no GitHub remote or no AI reviewer is installed; local quality gates (review + static + test) are authoritative in that case.

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
Quality gates passed? (review + static + test locally, configured AI reviewer(s) on GitHub if available)
Docs updated? (per Documentation Impact in plan)
PR created and CI green?
All BLOCKING/WARNING fixed?
Ticket → In Review?

All yes → Story is DONE (awaiting user merge)
```
