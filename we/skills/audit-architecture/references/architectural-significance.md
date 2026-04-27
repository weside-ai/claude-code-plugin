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

```bash
# How many other files import from this module?
mod_path = file_path → python_module_path
grep -rln "from ${mod_path} import\|from ${mod_path} import" <backend_root>
```

Count of distinct importing files = afferent coupling.

**Severity rule:**
- afferent > 10 + the file is unexpected → MAJOR (god-object risk)
- afferent 5–10 → MINOR (worth a split-evaluation)
- afferent < 5 → no finding (low-coupling unexpected hotspots are usually fine)

### AS-3 — Cohesion Heuristic

For each unexpected hotspot, list its **public symbols** (top-level `def`/`class` without `_` prefix):

```python
import ast
tree = ast.parse(file_text)
public_classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef) and not n.name.startswith("_")]
public_functions = [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]
public_methods = []  # methods of public classes
for n in tree.body:
    if isinstance(n, ast.ClassDef) and not n.name.startswith("_"):
        for m in n.body:
            if isinstance(m, ast.FunctionDef) and not m.name.startswith("_"):
                public_methods.append(f"{n.name}.{m.name}")
```

Then group public symbols by **verb-object pair semantics**:
- `send_*` / `stream_*` / `save_*` → conversation channel
- `get_threads` / `get_thread_*` / `delete_thread` / `undo_*` → thread lifecycle
- `update_*_state` / `memory()` → state + memory access

If public symbols cluster into 3+ distinct verb-object groups, the file is a **service-locator** not a single-responsibility class. MAJOR finding.

### AS-4 — Stability Probe

Heuristics:

```bash
# How many places break if this file's public API changes?
afferent_files = [from AS-2]
afferent_imports = total count of distinct symbols imported across all afferent files
```

If afferent_imports / afferent_files > 3 (each importer uses 3+ symbols on average), the API is wide → low stability → MAJOR (any change breaks many things).

### AS-5 — Testability Heuristic

```bash
# Are there protocol/interface files alongside?
ls <module_dir>/protocols.py
ls <module_dir>/interfaces.py

# Does the test suite mock the protocol or the concrete class?
grep -rln "Mock(spec=${ClassName}Protocol)" tests/
grep -rln "Mock(spec=${ClassName})" tests/
```

If only concrete-class mocks exist (no protocol-spec mocks), testability is theoretical. If no protocols.py exists, testability is structurally limited.

**Severity rule:**
- No protocols + concrete-only mocks → MINOR (testable but rigid)
- protocols.py exists but no Protocol-mocks → NIT (protocol unused)
- protocols.py + Protocol-mocks → no finding (well-isolated)

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

## Examples (predicted, from Phase 1 of weside-core 2026-04-27)

The 5 unexpected hotspots from the smoke-run:

| File | Predicted AS verdict |
|---|---|
| `api/v1/endpoints/chat.py` (2269 LOC) | MAJOR — endpoint metastasis: business logic in router |
| `config/settings.py` (1108 LOC, 138 commits) | MINOR — settings-as-bottleneck, but legitimate growth |
| `api/v1/endpoints/companions.py` (1410 LOC) | MAJOR — same fat-endpoint problem |
| `services/skill_agent_dispatcher.py` (14 primitives in 457 LOC) | MAJOR — densest per-LOC, 2 LangChain leaks (cross-references EB-1 from `encapsulation-boundaries`) |
| `tools/discovery.py` (1162 LOC, 2 langchain leaks) | MAJOR — tool-discovery should be LangChain-agnostic |

These are predictions; the actual lens-run will produce concrete findings with citations.

## Cross-References to Other Lenses

Architectural-significance findings are often **explained** by other lens findings:

- `chat.py` MAJOR (god-object) is **caused by** API → Service → CRUD layering not being enforced (could become a `schichten` Phase-2 finding for the subsystem owning chat.py)
- `skill_agent_dispatcher.py` MAJOR (god-object) is **partly explained by** EB-1 (LangChain leaks) — if it's leaking encapsulation, it's likely over-reaching its responsibility too
- `tools/discovery.py` MAJOR (god-object) is **partly explained by** EB-1 (LangChain leaks)

The skill emits cross-reference notes in findings to help the user see these patterns.

## Why This Lens?

A density-only Phase-1 output (the heatmap script alone) is informational: "these files are dense." Without architectural-significance, the human reader has to manually translate density into "is this a problem?".

This lens does that translation systematically. Each unexpected hotspot gets all 4 risk-lens questions answered with code evidence. The cohesion check (AS-3) is the most valuable — it tells you WHY a file is dense (legitimate orchestration vs accidental god-object).

The cost of skipping: Phase-1 produces a list of names; the user reads them and shrugs. Findings only emerge if the user has architectural intuition + time to manually deep-read each candidate. Most don't.

## Limitations

- AS-3 (cohesion heuristic) uses crude verb-object pattern matching. False positives on files where the pattern legitimately spans concerns (e.g., a CRUD module with `get_*` AND `update_*` AND `delete_*` — 3 verbs, but cohesive around one entity). Reviewer judgment required.
- AS-2 (coupling) only counts afferent imports, not transitive dependents. A file imported by 5 widely-used utility modules could have 50+ transitive dependents.
- AS-5 (testability) is structural-only; cannot detect tests that exist but mock the wrong things.
