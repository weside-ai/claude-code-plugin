---
type: story-plan
story: PROJ-12
epic: PROJ-1
depends_on: []
comments_read_through: none
created: 2026-01-05
status: approved
parallel_groups: []
---

# Plan: export the report as CSV

## Context

The report screen shows totals but nobody can take them elsewhere. This story adds a CSV
export to the report service, wired through the existing exporter seam.

## Acceptance Criteria

1. **Given** a report with three rows **When** the owner requests `GET /reports/7.csv`
   **Then** the response carries three data lines and a header [receipt]
2. **Given** an empty report **When** the exporter runs **Then** it writes only the header
   - nested detail: the header names every column
   [`ci`: `tests/test_export.py`, a unit test; staging cannot build an empty report]
3. **Given** the report screen **When** the owner taps Export **Then** a file is saved
   [walk: owner · report screen · why: the button moved]

## User Journey

Purely technical: the export endpoint is called by the client.

## Testing Requirements

- AC2: `tests/test_export.py` (new).

## Verification

- **Oracle:** cli — the endpoint answers.
- **Seed:** `make seed`
- **Asserted:** three data lines.
- **Not proven:** the client button.

## Technical Approach

Grep-derived, no code graph.

## Implementation Phases

### Phase 1: exporter

- **Goal:** the CSV writer.
- **Files:**

  - `src/report/export.py` (new) — the writer, see `src/report/base.py:10-20`
  - `tests/test_export.py` (new)
  - `docs/guides/export.md` — a mention of `format.csv` and `README.md` in prose

- **Risk:** ordinary — none.
- **Approach:** a writer.

### Phase 2: shared parser

- **Goal:** the parser lives in the library.
- **Repo:** lib-repo
- **Files:**

  - `lib/csv/parse.py` (other repo)

- **Risk:** ordinary — none.
- **Approach:** a function.

## Out of scope

- Excel export.

## Constraints and Pins

**Constraints:** the exporter seam. **Pins:** JSON stays.

## Design Decisions

| Decision | Alternatives considered | Why this, decided by whom |
|---|---|---|
| CSV | XLSX | simple. Product |

## Security Review Required

No — read-only.

## Documentation Impact

- **Docstrings** — the writer.
