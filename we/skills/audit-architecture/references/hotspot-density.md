---
name: audit-architecture-hotspot-density
description: Phase 1 method — primitive-density-driven hotspot map for finding architectural problem zones across subsystems
type: reference
---

# Hotspot Density (Phase 1)

## Purpose

Surface architectural problem zones by measuring **primitive composition density** per file. The hypothesis: load-bearing modules compose many Platform Primitives. Subsystem-bounded audits miss modules that *span* subsystems; the density map catches them.

## When to apply

- **Phase 1** of `/we:audit-architecture` — runs by default after Healthcheck.
- **Standalone:** `/we:audit-architecture --hotspots-only` (≈10 sec runtime).
- **Project requirement:** the project's `.audit-architecture.yml` should define `hotspots.expected_hubs:` for the expected-vs-unexpected classification to work; absent it, every hotspot is "unexpected" by default.

## Method

The script is `scripts/audit-hotspots.py`. For each Python file under `backend_root` (excluding tests, migrations, and `__init__.py`):

The executed formula is `compute_score()` in `scripts/audit-hotspots.py` — that code is the
owner; this block explains it and must follow the script if they ever differ:

```
score = primitives_count * 5     # how many Platform Primitives this file composes
      + LOC / 50                  # complexity proxy
      + churn                     # git commits in window (default: 6 months)
      + bypasses_count * 3        # # *-BYPASS-OK: knowing-divergence count
      + private_reach_ins * 3     # imports of `<core>/_*` from outside core
      + total_leaks * 4           # `from <vendor>` outside configured homes
```

Primitive detection is regex-based on surface symbols (imports + class names). Catalog: `scripts/primitives.default.yml` ships with the plugin; project YAML can override via `primitive_detectors:`.

Top-N (default 15) sorted descending. Each entry is auto-classified:

- **Expected** — file path is in `hotspots.expected_hubs:` (documented density-hub, no surprise).
- **Unexpected** — surprising hotspot. These become candidates for Phase-3 architectural-significance review.

## Score Tuning

The default coefficients reflect a Companion-style backend architecture (LangGraph agent + primitive-based subsystems). Tuning rationale:

| Component | Coefficient | Why |
|---|---|---|
| primitives | 5 | Each primitive is a fully-formed concept; composing 5 = significant orchestration |
| LOC / 50 | 1 / 50 | LOC is a weak proxy alone; only differentiates within similar primitive-counts |
| churn | 1 | Direct churn count; high-churn files are riskier regardless of density |
| bypasses | 3 | Each `*-BYPASS-OK` is a deliberate divergence; 3 bypasses = significant accumulated risk |
| reach-ins | 3 | Same weight as bypass (encapsulation breach is comparable to primitive bypass) |
| leaks | 4 | Vendor leaks are more severe than reach-ins (cross-architectural-layer concern) |

Projects can override via project-config — but the score is a *ranking*, not an absolute risk score. The coefficients only matter for relative ordering of files.

## Expected vs Unexpected Classification

A documented hub is a file the team knows is dense — by design. Typical
shape of an `expected_hubs:` block for a Companion-style backend:

```yaml
hotspots:
  expected_hubs:
    - apps/backend/app/main.py                              # app factory (FastAPI / similar)
    - apps/backend/app/companion/core/being.py              # CONSCIOUSNESS hub
    - apps/backend/app/companion/core/_langgraph.py         # agent definition
    - apps/backend/app/companion/gateway/service.py         # FAT entry point
    - apps/backend/app/api/deps.py                          # auth context chain
    - apps/backend/app/config/llm.py                        # LLM factory chokepoint
    - apps/backend/app/config/_instrumented_model.py        # observability chokepoint
    # …add other files the team knows are dense by design.
```

A file in the top-N that is NOT in `expected_hubs:` is the audit signal.
Common surprise shapes from real runs:

| Rank | File shape | Why surprising |
|---|---|---|
| 2 | `api/<endpoint>.py` (~2k LOC) | "Endpoint" carrying business logic → metastasis |
| 4 | `config/settings.py` (~1k LOC + heavy churn) | "Config" file growing into a god-object |
| 8 | A second fat endpoint module | Same fat-endpoint problem, second instance |
| 13 | `services/<dispatcher>.py` (densest per-LOC + framework leaks) | Dispatcher accreted unrelated logic |
| 15 | `tools/discovery.py` (~1k LOC + framework leaks) | Tools should be framework-agnostic |

## Output Format

Default: markdown to stdout. With `--write`: `<findings_dir>/<date>-hotspots.md`.

```markdown
---
type: audit
domain: [platform]
status: current
scope: hotspots
date: YYYY-MM-DD
---

# Architecture Hotspot Heatmap — YYYY-MM-DD

Scanned **N** Python files under `<backend_root>` ...

## Score formula
[code block]

## Top N by composite score

| # | File | Hub? | Score | Prim | LOC | Churn | Byp | Leak | Reach |
| ... |

## Surprise hotspots (M of top N)

[Top 5 unexpected, with full primitive composition + leaks/reach-ins detail]

## Per-file deep-dive
python3 audit-hotspots.py --file <path>
```

## Heatmap Diagram (optional, generated by Phase 4)

If Phase 4 runs after Phase 1 + Phase 2, the master.md aggregates a `heatmap.mmd` — the Mermaid
quadrant template, axis semantics, and severity coloring live in `visualization.md` § Type 3 —
Hotspot Quadrant.

## How Phase 1 Findings Become Phase 3 Input

Files marked **unexpected** in Phase 1 are passed to Phase 3's **architectural-significance** lens (see `architectural-significance.md`). That lens applies a 4-question risk-lens (coupling/cohesion/stability/testability) to each unexpected hotspot, producing concrete findings.

Without `architectural-significance` enabled, Phase 1 output is informational only — it identifies candidates without classifying them as findings.

## Tuning the `since` Window

Default: `"6 months ago"`. Tradeoffs:

- **Shorter** (e.g., `"3 months ago"`) — focuses on currently-active areas, reduces noise from old churn
- **Longer** (e.g., `"1 year ago"`) — full architectural-trend view; useful in retrospectives

`/we:audit-architecture --since="3 months ago"` overrides the YAML default.

## Dependencies

- `git log` — for churn computation
- `python3` + PyYAML — script dependencies
- The script does NOT require pip install at the project level; PyYAML usually present in any Python project. If absent, error-out with helpful message.
