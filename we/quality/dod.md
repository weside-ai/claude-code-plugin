# Definition of Done (DoD)

**A story is DONE when all criteria below are met.**

A repo can extend this checklist with its own criteria in `.weside/dod.md` (created by `/we:setup`); the `we:ac-reviewer` agent reads it additively — both the checklist below and the repo file apply, the repo file never replaces this one.

---

## Checklist

### Code Quality

- [ ] Code implemented and functional
- [ ] Acceptance Criteria individually verified (each AC checked with evidence)
- [ ] Feature REACHABLE: User can navigate to the feature (button/route/screen)
- [ ] End-to-end: Complete user flow works, not just individual parts
- [ ] No unresolved TODO/FIXME left
- [ ] **Every planned phase landed** — each plan `### Phase` block's `**Files:**` actually changed in this diff; a phase committed by someone other than its worker is named in the PR body with who did it and why.
- [ ] **Parallelisation considered** — for stories with 3+ independent implementation phases: `parallel_groups` is set in the plan frontmatter, or there is an explicit note in the plan explaining why phases must be sequential. Skip for stories with 1–2 phases.

### Architecture Compliance

- [ ] Architecture patterns from plan followed
- [ ] ADRs referenced in story were followed
- [ ] Security patterns applied (if Security Review = Yes in plan)
- [ ] **Deliberate bypasses justified** — where the repo has a bypass convention: every new
      annotation carries a specific reason, and a grown register is either cited to an ADR or
      justified in the PR body. If the repo ships a register generator, it was re-run and the
      result committed. No such convention → skip.

### Verification (observed, not inferred)

- [ ] **The behaviour was observed against a running instance** — via the oracle the ACs demand: the project's CLI/API by default, a UI walkthrough as soon as an AC says the user can see, tap or reach something, a named substitute where neither is possible, or an explicit `not-applicable` with its reason. Green tests do not discharge this: they share the blind spots of whoever wrote the code. Contract: `references/verification.md`; commands: `<repo>/.weside/verify.md`.
- [ ] **The PR carries a `## Verification` block** — oracle, seed, what was asserted, what stays unproven. No block, no claim of verified.
- [ ] **Any missing CLI verb shipped with the story** — if verifying needed a multi-step shell dance the project's CLI cannot do, that verb was added, not worked around.

### Testing

- [ ] Test types from plan implemented (Unit/Integration/E2E)
- [ ] Coverage meets project thresholds (verified by CI on push — not a local gate)
- [ ] **Affected tests pass locally** — tests covering the diff (mapped paths for pytest, `--findRelatedTests` for Jest); the full suite runs in CI. Fall back to the full local suite when the diff touches `conftest.py`, jest config, fixtures, or >50 files.
- [ ] **Test quality per `references/test-discipline.md`** — no implementation-coupled tests, no tautological assertions, mocks at system boundaries only. Applies at every `test_discipline` level (the level only decides *when* tests are written).

### Post-Implementation Semantic Checks

Verify each item that applies; skip the rest. These are the classes that pass unit tests and
break in production.

- [ ] **Migrations run and reverse** — applied locally, and idempotent (guarded DDL, conflict-safe
      data writes) so a re-run is not a failure
- [ ] **State wiring complete** — a new data field flows through every layer: storage → service →
      API → UI. A field that stops halfway is a feature the user cannot reach.
- [ ] **Timezone handling** — local-date logic uses local getters, never a UTC-truncated ISO string
- [ ] **Range validation** — date/number ranges guard the inverted case
- [ ] **String length validation** — text columns validate length before insert
- [ ] **Index column order** — composite indexes ordered by selectivity, left to right
- [ ] **Test depth** — tests assert behaviour and arguments, not merely that a call returned
- [ ] **i18n complete** — user-facing strings go through the translation layer (if the project has one)
- [ ] **Horizontal scalability** — no new process-local mutable state that outlives a request
      (in-process caches, module/class-level mutable containers, memoised impure functions,
      in-process locks used across requests). Such state belongs in a database, cache, or queue;
      a deliberate exception carries an inline `# SCALABILITY-EXEMPT: <reason>`.

Repo-specific classes (an ORM-cache rule, a reference-data layer, a hot-path convention) belong
in `.weside/dod.md`, which is read additively alongside this checklist.

### Evidence

- [ ] **Success claims carry their output** — "tests pass", "it works", "fixed" are assertions.
      Each is backed by the command and its actual output, in the PR description, a commit message,
      or an inline comment. An assertion without output fails this gate.

### Quality Gates

- [ ] AC-review passed (`ac_verified` checkpoint — `/we:ac-review` / `we:ac-reviewer`)
- [ ] Bug-hunt passed (`review_passed` checkpoint — Codex adversarial-review or Claude's native `/code-review`)
- [ ] `/we:static` passed (static_analysis_passed checkpoint)
- [ ] `/we:test` passed (test_passed checkpoint)
- [ ] AI-reviewer threads resolved on GitHub — the repo's configured review gate(s) block on unresolved BLOCKING/WARNING (Critical/Major) threads. Use `/we:ci-review` to fix and resolve all bot threads after PR creation. Skip if no GitHub remote or no AI reviewer is installed; local quality gates (review + static + test) are authoritative in that case.

### Documentation

Documentation is a **cascade**, not a checklist. Each step applies only when the one above
it cannot carry the knowledge — most changes stop at the first.

- [ ] **Behaviour changed → the docstring at the site was updated.** Always, and first.
      What it does, which trap it avoids, what a caller must not do — written where the
      code is, because that is the only place the next reader is guaranteed to look. A
      change whose sole record lives in a file elsewhere in the tree has, in practice, no
      record at all.
- [ ] **Interplay across module boundaries changed → the one thematic architecture doc.**
      Only for knowledge that genuinely spans files no single docstring owns: a flow
      through several subsystems, a contract between them. A changed user-facing flow is
      this case — it updates the journey doc rather than spawning a new one.
- [ ] **Hard to reverse, surprising, real trade-off → an ADR.** Rare by construction.
- [ ] **A NEW doc carries its justification** — one sentence on why the code cannot hold
      this. "It felt like documentation" is not one; absent a reason it belongs in a
      docstring. Every doc created is a doc someone must keep true.
- [ ] **A doc contradicting the code was corrected or deleted** — never deferred, never
      annotated as outdated. This is the class that survives longest, because nothing
      fails when prose goes stale, and a wrong doc costs more than a missing one.
- [ ] **Generated artefacts regenerated** — API spec/types, CLI reference, any register the
      repo ships a generator for. Codegen, not prose; it never substitutes for the first item.
- [ ] Documentation Impact from the plan addressed (if specified)

### CI/CD

- [ ] PR created (pr_created checkpoint)
- [ ] CI passed or reviews green
- [ ] All BLOCKING/WARNING issues fixed

### Ticketing

- [ ] Ticket moved to "In Review"
- [ ] User reviewed and merged
- [ ] Ticket moved to "Done" — only on the human's explicit word after their merge (`/we:orchestrate` Step 10), never as a pipeline step

---

## Issue Severity

A DoD row that Fails blocks exactly like an unmet acceptance criterion — there is no second,
softer tier for "only" the DoD.

| Level | Action |
|---|---|
| **BLOCKING** | MUST fix |
| **WARNING** | MUST fix |
| **INFO/NITPICK** | Fix or document skip reason |

---

## Who checks this

`we:ac-reviewer` fills a row per applicable item above; its output format lives in
`agents/ac-reviewer.md`. The bug-hunt engine reports separately — `worker-dispatch.md`
§ Bug-hunt dispatch.
