---
name: audit-architecture-architectural-significance
description: Phase 3 default lens — applies a 4-question risk lens to each unexpected hotspot from Phase 1
type: reference
---

# Architectural Significance (Phase 3, default)

## Purpose

For each **unexpected hotspot** from Phase 1, apply the four classical software-architecture risk questions:

1. **Coupling** — how many things depend on it (afferent fan-in)?
2. **Cohesion** — does it have a single responsibility?
3. **Stability** — can it change without breaking dependents?
4. **Testability** — can it be tested in isolation?

This is the "Enterprise-Architect Risk Storming" of Simon Brown applied automatically to candidates rather than hand-picked diagrams.

## When to apply

- **Phase 3** of `/we:audit-architecture` — runs by default in `cross_cutting:` lenses.
- **Standalone:** `--lens=architectural-significance`
- **Project requirement:** Phase 1 (Hotspot Map) must have been run, OR `expected_hubs:` must be defined in `.audit-architecture.yml` (so the lens can identify candidates).

## Method

Five steps per unexpected hotspot:

### AS-1 — Identify Candidates

Pull from Phase 1 output: files in the top-N where `expected: false`. If Phase 1 wasn't run, run it first internally (the script invocation is fast).

### AS-2 — Coupling Measurement (Afferent)

Count the **distinct files that import this module**. That count is its afferent coupling.

| Afferent | Verdict |
|---|---|
| > 10, on an unexpected hotspot | MAJOR — god-object risk |
| 5–10 | MINOR — worth a split-evaluation |
| < 5 | no finding — a low-coupling hotspot is usually just a big file |

### AS-3 — Cohesion Heuristic

List the file's **public symbols** — top-level classes and functions plus the public methods of
public classes. Parse the AST rather than grepping, so decorators and nesting don't fool you.

Then group them by **verb-object semantics**: which noun does each verb act on? Three or more
distinct groups means the file is a **service-locator**, not a single-responsibility module → MAJOR.

This is the most valuable check in the lens: it tells you *why* a file is dense — legitimate
orchestration, or an accidental god-object.

### AS-4 — Stability Probe

Across the afferent files from AS-2, count the distinct symbols each imports. An average above
~3 per importer means a **wide API**: any change to it breaks many callers at once → MAJOR.

### AS-5 — Testability Heuristic

Two questions: does an interface/protocol declaration sit alongside the implementation, and do the
tests mock *that* or the concrete class?

| Protocol declared | Tests mock | Verdict |
|---|---|---|
| no | the concrete class | MINOR — testable but rigid |
| yes | the concrete class | NIT — the protocol is unused |
| yes | the protocol | no finding — well isolated |

## Output Format

Per unexpected hotspot, produce one finding-block:

```markdown
### AS-MAJ-N — <file> is a god-object candidate

**Severity:** MAJOR
**Lens:** architectural-significance
**Cite:** `<file>` (whole file)

**Why this hotspot is unexpected:** Phase-1 score X (rank #N), not in `expected_hubs`. Composes M primitives in K LOC.

**Risk lens:**
- **Coupling:** afferent = 11 importers (high)
- **Cohesion:** 17 public methods cluster into 3 verb-object groups (Thread / Message / Memory)
- **Stability:** API width 4 symbols/importer on avg (high) — breaking changes propagate
- **Testability:** `protocols.py` exists ✓, but tests primarily mock concrete classes ✗

**Implication:** This file is acting as a service-locator combining 3 unrelated aggregates.
Any change to one aggregate's contract risks breaking all 11 dependents.

**Fix proposal:** split into 3 separate facades:
1. `<ConceptA>Facade` — methods related to <pattern1>
2. `<ConceptB>Facade` — methods related to <pattern2>
3. `<ConceptC>Facade` — methods related to <pattern3>

Use Composition: original class becomes a thin coordinator that delegates to the 3 facades.

**Effort:** L (4-8h plus call-site updates across 11 files).
```

## The shapes this lens surfaces

A Phase-1 run typically produces a handful of unexpected hotspots. The recurring shapes:

| Shape | Verdict | Why |
|---|---|---|
| A fat endpoint/route module (>1k LOC) | MAJOR | endpoint metastasis — business logic living in the router |
| A settings/config module with heavy churn | MINOR | bottleneck by nature; growth is usually legitimate |
| A dispatcher with the highest primitive-density per LOC | MAJOR | accreted unrelated responsibilities |
| A "framework-agnostic" module that imports the framework | MAJOR | cross-references the `encapsulation-boundaries` lens |

**Findings explain each other.** A god-object verdict is often *caused by* a layering violation
(business logic in the router) or *accompanied by* a vendor leak — when both fire on the same file,
say so in the finding. That pairing is what turns two isolated observations into a diagnosis.

## Why This Lens?

Phase 1 alone is informational: "these files are dense." Translating density into "is this a
problem?" is what this lens does systematically — every unexpected hotspot gets all four risk
questions answered with code evidence. Skip it and Phase 1 produces a list of names the reader
shrugs at.

## Limitations — name them in the finding

- **AS-3** groups by verb-object pattern; a CRUD module over one entity legitimately spans
  `get_*`/`update_*`/`delete_*`. Reviewer judgment required.
- **AS-2** counts direct importers only. A file imported by five widely-used utilities can have
  fifty transitive dependents.
- **AS-5** is structural: it cannot tell that a test exists but mocks the wrong thing.
