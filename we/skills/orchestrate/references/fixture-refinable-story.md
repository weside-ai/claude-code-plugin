---
story: FIXTURE2
epic: rehearsal
status: draft
depends_on: [FIXTURE]
parallel_groups: []
---

# Plan: Rehearsal fixture (refinable) — add rehearsal_double()

> **Template (refinable counterpart).** `/we:orchestrate --rehearsal --refine-ahead` copies this file
> into the throwaway repo as `docs/plans/FIXTURE2-story.md`. It is intentionally **un-refined** — it
> fails the DoR scan (`_body_is_refined`: no GWT acceptance criteria, no `### Phase` header), so it
> lands in the `refinable` bucket. It `depends_on` the refined `FIXTURE` story, so with
> `REFINABLE_DEP_MODE="refined"` it is refinable while FIXTURE builds — exercising the chain-overlap
> the refine lane exists for. The P3 go/no-go: a refiner-teammate turns THIS stub into a DoR-passing
> plan (full Context + GWT ACs + Phase headers) without stalling, and the Lead's `story ready` then
> shows it left `refinable`.

## Intent (front-loading for the refiner — NOT the finished plan)

Add a second trivial-but-real pure function `rehearsal_double(n: int) -> int` that returns `2 * n`,
with a unit test. It mirrors `rehearsal_noop()` from FIXTURE. The refiner must expand this stub into
the full story-plan sections (Context narrative, numbered GWT Acceptance Criteria, Technical Approach,
`### Phase` implementation steps with a `**Files:**` line, Testing Requirements, Design Decisions).
There is no real design fork here — the refiner has everything it needs; it should not need to ask.
