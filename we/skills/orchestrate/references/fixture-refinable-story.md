---
story: FIXTURE2
epic: rehearsal
status: draft
depends_on: [FIXTURE]
parallel_groups: []
---

# Plan: Rehearsal fixture (refinable) — add rehearsal_double()

> **Template (unrefined counterpart).** `/we:orchestrate --rehearsal` copies this file into the
> throwaway repo as `docs/plans/FIXTURE2-story.md`. It is intentionally **un-refined** — it fails
> the DoR scan (no GWT acceptance criteria, no `### Phase` header), so `story state` puts it on
> `draft` while its sibling sits on `refined`. That pair is the point: one epic, two maturities,
> and the run must produce a REFINE and a DEVELOP in the same pass. It `depends_on` FIXTURE, which
> a refine dependency accepts as met — so planning runs against FIXTURE's seam while FIXTURE
> builds. Pass: a refiner turns THIS stub into a DoR-passing plan without stalling, and the Lead's
> re-read shows it left `draft`.

## Intent (front-loading for the refiner — NOT the finished plan)

Add a second trivial-but-real pure function `rehearsal_double(n: int) -> int` that returns `2 * n`,
with a unit test. It mirrors `rehearsal_noop()` from FIXTURE. The refiner must expand this stub into
the full story-plan sections (Context narrative, numbered GWT Acceptance Criteria, Technical Approach,
`### Phase` implementation steps with a `**Files:**` line, Testing Requirements, Design Decisions).
There is no real design fork here — the refiner has everything it needs; it should not need to ask.
