---
name: test-economy
description: Which tests a build worker writes — the leading question, extend before you add, the risk stagger, the two malformed kinds, the cheapest stage — and what the PR's test line shows. Shared by /we:develop, /we:ci-review, /we:plan-story and the acceptance lens.
owner: hr
review: 2026-12-02
---

# Test economy

A test earns its place when it would fail for a defect a user or a caller would notice, and no
cheaper check already fails for it. `test_discipline` (`.weside/config.json`) says *when* tests are
written; this file says *which*. The rule runs as a trial; the owner role reviews it on the
`review:` date above against the flow report's test and escape rows (`scripts/flow_report.py`).

## Contents

The leading question · Risk stagger · Extend before you add · No test pins text · A red arm is not
a unit test · The cheapest stage · What the PR line shows.

## The leading question

Before every new test: **which defect does this test catch that no existing test catches?** No
answer → no new test. An answer like "a wrong amount" or "another tenant sees the data" → the test
is written, always.

## Risk stagger

The measure is the repo's own risk classifier (`risk.command` in the crew, else
`scripts/risk_paths.py` over `.weside/risk-paths`) plus the globs under `tests.no_cap_paths` in
`.weside/config.json`: the risk-path file is never complete, so a repo also names its risk domains
by path (billing, credit, entitlement, auth, tenant isolation, consent, migrations).

- **A file the classifier hits or `no_cap_paths` names:** no cap. The rule turns around: every
  boundary value, every role and every amount gets a named case, and each boundary keeps a
  repeatable red arm through the gate's own arm (§ A red arm is not a unit test). The lift is per file, never per PR: a PR that touches one risk path frees
  none of its other tests.
- **Every other file:** at most one test per AC, fewer where two ACs meet the same behaviour, plus
  the edge cases the plan names; not one per line, per branch or per review finding. A large input space takes a property test, never
  a long parametrize table.

## Extend before you add

Find the test that already exercises the behaviour and add the assertion or the case there. A new
test function needs a behaviour no existing test reaches; the report names that behaviour. A review
finding becomes an assertion in the existing test of that behaviour; a new test only when the
finding shows a behaviour no test reaches. A request for one more test of a behaviour that is
already tested is answered with the test that covers it.

| Bad | Good |
|---|---|
| A finding "404 not handled" → new `test_fetch_returns_none_on_404` beside `test_fetch_errors` | one more case in `test_fetch_errors`'s table, and the report names it |
| A reviewer asks for a test of the retry delay → `test_retry_delay_again` | the reply cites `tests/test_client.py::test_retry_backoff`, which asserts the delay already |

## No test pins text

Comments, docstrings, workflow YAML, docs and log wording carry no test. Where a structure must
hold, check the structure once (a schema, a parsed key), never the wording.

| Bad | Good |
|---|---|
| `assert "retries three times" in read("docs/client.md")` | none: the doc is read by people |
| `assert "timeout-minutes: 30" in workflow_text` | `yaml.safe_load(workflow)["jobs"]["test"]["timeout-minutes"] == 30`, once, in the workflow check |

## A red arm is not a unit test

A new gate proves it can fail through the gate's own arm (the repo's gate registry or the gate's
fixture), run once before the PR; it never becomes a test that mutates code on every CI run.
Precondition: the gate runs on every PR that touches its subject. Where CI may skip the gate by
diff, the arm stays a test until that is closed.

## The cheapest stage

A pure function before a database, a database before a real turn or a real wait: each test runs at
the cheapest stage that can still fail for its defect.

## What the PR line shows

`scripts/test-delta.py` prints the PR body's line: functions and parametrize cases added and
removed, the new tests above `tests.slow_seconds` when the last local run left a JUnit file, the
ratio of added test lines to added code lines marked above `tests.max_ratio`, the tables above
`tests.max_parametrize`, and the files listed as `risk path: no cap`, which stay out of the ratio
and the table mark. `tests.exclude_paths` names globs no count looks at. The keys sit in
`.weside/config.json` under `tests`; each mark is a signal for the author and the reviewer, never a
merge gate.
