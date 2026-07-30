---
name: audit-architecture-doc-vs-reality-drift
description: Phase 3 default lens — extracts invariants from primitive-detail-docs and verifies each in code (✓/⚠/✗/?)
type: reference
---

# Doc-vs-Reality Drift (Phase 3, default)

## Purpose

For every primitive-detail-doc that declares explicit invariants (`**I1.**`, `**I2.**`, ...), verify each invariant in code. Output: a drift matrix with one row per invariant, status ✓ (holds) | ⚠ (partial) | ✗ (violated) | ? (unverified).

This is the **highest-finding-value lens** because it converts implicit "the doc says X" into explicit "the code says Y, X is violated, here's the file:line evidence."

## When to apply

- **Phase 3** of `/we:audit-architecture` — runs by default in `cross_cutting:` lenses.
- **Standalone:** `--lens=doc-vs-reality-drift`
- **Project requirement:** primitive-detail-docs follow the canonical 8-section structure (see `findings-template.md` § Primitive Detail Doc Format), specifically with explicit numbered invariants `**I1. <Name>.**`, `**I2. ...**`.

## Method

Five steps:

### Step 1 — Discover Primitive Docs

```bash
# Configured glob in healthcheck.doc_drift.target_glob
ls docs/architecture/primitives/*.md
```

A mature backend often has 20–40 primitive docs. Each is a candidate.

### Step 2 — Extract Invariants

Manual pattern (v3.0): read each doc's `## Invariants` section, identify lines starting with `**I<N>.**` followed by an invariant statement.

Optional automation (`scripts/extract-invariants.py`, future): parse docs as markdown, extract `**I<N>.**` patterns, output `{primitive_name: [(I1_text, I2_text, ...)]}` JSON.

For v3.0, the manual catalog approach: maintain a small `invariant_catalog.yml` per project listing the invariants the team cares about + their verification recipe.

```yaml
# Optional in .audit-architecture.yml
invariant_catalog:
  observability-triad:
    - id: I1
      claim: "No print() in production code"
      verify_grep: "^\\s*print\\("
      verify_excludes: [docs/, tests/, <admin-app>/, <support-app>/]
    - id: I3
      claim: "Every request has a trace/correlation ID"
      verify_grep: "bind_context|RequestIDMiddleware"
      verify_must_exist: true   # this pattern MUST appear in middleware/
      verify_must_be_in: [<backend>/middleware/]
    # ...
```

If the catalog is absent, the lens runs in **manual mode**: it flags primitive docs WITH explicit invariants and tells the auditor to manually verify each.

### Step 3 — Verify Each Invariant

For invariants with `verify_grep` defined, run the grep + check:
- `verify_must_exist: true` → at least one match in the codebase, else `✗`
- `verify_must_be_in: [paths]` → ALL matches must be inside listed paths, else `✗`
- `verify_excludes: [paths]` → matches in these paths are ignored
- absent → manual verdict: `?`

Output for each invariant:
```
{primitive: "observability-triad", id: "I3", verdict: "✗", evidence: "no match in <backend>/middleware/"}
```

### Step 4 — Render Drift Matrix

Render `drift-matrix.mmd` per the template in `visualization.md` § Type 4 — Drift Matrix
(one subgraph per primitive doc, one node per invariant with verdict `✓/⚠/✗/?` + summary,
severity classes from the registry there).

### Step 5 — File Findings for Drifts

Each `✗` becomes a finding:

```markdown
### DR-MAJ-N — observability-triad I3: no trace_id middleware

**Severity:** MAJOR
**Lens:** doc-vs-reality-drift
**Primitive:** observability-triad
**Invariant:** I3 — "Every request has a trace/correlation ID"
**Cite:** `docs/architecture/primitives/observability-triad.md` claims it; `<backend>/main.py:951–1029` does not register a TraceID middleware.

The primitive doc says: *"The FastAPI middleware sets `trace_id` on the structlog
context so every log line from one request is correlateable."*

The code says: 5 middlewares registered (ProxyHeaders, VersionCheck, CORS,
SlowAPI, SecurityHeaders), none of which bind `trace_id`. `bind_context()` is
defined in `core/logging.py:275` but only referenced from its own docstring.

**Resolution paths:**
1. Add a `RequestIDMiddleware` that generates UUID and calls `bind_context(request_id=uuid)` per request — closes the gap.
2. Update the primitive doc to admit the actual correlation mechanism (e.g., Loki transport-level request-id) — closes the doc-drift but doesn't add the structured field.

**Effort:** S (1-2h for option 1, 30 min for option 2).
```

Each `⚠` becomes a MINOR finding.
Each `?` becomes a NIT (audit incomplete).
Each `✓` is reported but not a finding.

## Verdict Semantics

- **✓ (holds)** — code unambiguously satisfies the invariant. Evidence: grep produced the expected matches in the expected places.
- **⚠ (partial)** — invariant holds in some places but not all. Common case: documentation-by-discipline rules (e.g., "no PII in logs") that have no structural enforcement.
- **✗ (violated)** — code contradicts the invariant. Evidence: grep produced the wrong shape (e.g., expected match doesn't exist; forbidden pattern exists).
- **? (unverified)** — invariant cannot be checked by grep alone. Common case: behavioral invariants ("at most one Haiku call per event"). Mark for manual review.

## Output Format

`<findings_dir>/cross-cutting.md` includes a section:

```markdown
## Doc-vs-Reality Drift Matrix

[Mermaid drift-matrix.mmd block]

### Drifts found (2 ✗, 1 ⚠, 0 ?)

[Findings list, severity-tagged]
```

## What the verdicts look like in practice

A mature observability primitive doc carries on the order of eight invariants. A real run mixes all
four verdicts, and the pattern is stable across projects:

| Invariant shape | Typical verdict | Why |
|---|---|---|
| "No `print()` in production code" | ✓ | structurally enforceable, and usually enforced |
| "Log key-value pairs, not interpolated strings" | ✗ | discipline-only; interpolated calls accumulate |
| "Every request carries a correlation id" | ✗ | the middleware is often missing while the helper exists, referenced only from its own docstring |
| "No PII in logs" | ⚠ | a secrets filter exists; user content is not covered |
| "All model calls go through the instrumented wrapper" | ✓ | a chokepoint that a leak-count check can confirm |
| "Metrics labels stay low-cardinality" | ✗ | per-user labels creep in one counter at a time |

The ✗ rows are where the value is: each was a documented promise the code had quietly stopped
keeping. Two of the three shapes above were found *by accident* before this lens existed — a grep
run for another reason. That is exactly the luck this lens removes.

## Why This Lens Matters

In the v2.19.0 run, doc-vs-reality drifts were found by accident — a grep for f-strings was triggered while reading `core/logging.py`, the missing trace_id middleware was noticed when reviewing `main.py`'s middleware list. Without this lens, finding these drifts depends on the auditor's habit of reading docs before code AND remembering specific claims.

The lens makes it systematic: every `**I<N>.**` in every primitive-doc gets a verdict.

The cost of skipping: documented-but-not-implemented invariants accumulate. Each accumulation makes the primitive-doc less trustworthy. Eventually the docs become aspirational fiction, and the team stops reading them — at which point the "Platform Primitives" architecture itself loses its enforcement mechanism.
