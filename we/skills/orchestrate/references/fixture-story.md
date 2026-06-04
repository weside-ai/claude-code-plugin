---
story: FIXTURE
epic: rehearsal
status: approved
parallel_groups: []
---

# Plan: Rehearsal fixture — add rehearsal_noop()

> **Template.** `/we:orchestrate --rehearsal` copies this file into a throwaway repo as
> `docs/plans/FIXTURE-story.md`. It is intentionally trivial but **real** — a genuine diff so
> the build's review/test/PR steps actually run. Never built into a real product.

## Context

A throwaway fixture Story used to rehearse the full `/we:orchestrate` → builder → `/we:build`
pipeline without touching real product code. Its only purpose is to give the build pipeline a
genuine, trivial diff to review and test so skill frictions surface. Not shipped.

## Acceptance Criteria

1. **Given** the rehearsal package, **When** I call `rehearsal_noop()`, **Then** it returns the
   integer `42`, and a unit test asserts this.

## Technical Approach

Add a pure function `rehearsal_noop() -> int` and a test asserting it returns `42`.

### Phase 1: Add function + test

- **Goal:** `rehearsal_noop()` returns 42 with a passing test.
- **Files:** the package's main module + a new test file.
- **Approach:** TDD — write the failing test first, then the function.

## Testing Requirements

- **Unit:** a test asserts `rehearsal_noop() == 42`.
