---
name: audit-architecture-spec-v3
description: Canonical architecture spec for the v3 rewrite of the /we:audit-architecture skill — pipeline phases, lens library, YAML schema, output format, CLI surface
type: reference
---

# SPEC v3 — `/we:audit-architecture`

**Status:** Draft for v2.20.0 release of the `we` plugin.
**Supersedes:** Implicit v2 design encoded in v2.19.0 `SKILL.md`.
**Audience:** Skill maintainers (this is the *why* and *what*; `SKILL.md` is the *how*).

---

## 1. Goals

The skill is a multi-phase architecture-audit tool that produces severity-tagged findings with visual intensity, runnable on demand against any backend project that adheres to a Platform-Primitives architecture style.

**Primary goals:**

1. Surface **architectural problem zones** the human reader could not find by reading code linearly — across both subsystem boundaries and cross-cutting concerns.
2. Verify that **documented invariants** (in primitive-detail-docs) actually hold in code. Drift is the most valuable finding type.
3. Make finding **intensity visible** — Mermaid diagrams with severity-color overlays, not buried in a long markdown.
4. Be **reusable**: the skill ships in a plugin, configured via a single project YAML.
5. Be **incremental**: every phase can be skipped or run in isolation. The skill is a hammer that can also be a tweezers.

**Non-goals:**

- Auto-fix of findings. Output is recommendation; user decides.
- Replacing test execution. Coverage-mapping yes, test-run no.
- Replacing deep static-analysis tooling (`pydeps`, `vulture`, `bandit`, `pip-audit`). The skill is *complementary* — it answers "is the architecture being upheld?" while those tools answer "is the code clean/safe?".

---

## 2. Why v3 (Problem Statement)

v2 (Healthcheck → Subsystem-Deep-Read → Findings) was applied across four
subsystems of a real backend project as a shakedown. Result on the order of
two dozen findings, mostly MAJOR/MINOR.

The run revealed five structural gaps in v2:

| # | Gap | Concrete shape |
|---|---|---|
| 1 | Subsystem audits don't catch modules *between* subsystems | A multi-thousand-LOC endpoint module touching nine primitives — invisible because not in any subsystem's `paths:` |
| 2 | High-level conceptual lenses absent | "Does the system stay logically whole?" / "Are the major components separable?" — most valuable architectural questions, no mechanism |
| 3 | Doc-vs-Reality drift only found accidentally | One subsystem audit found three invariant violations by happenstance grep, no systematic mechanism |
| 4 | Severity invisible in diagrams | Mermaid diagrams had no risk-storming colors despite findings being severity-tagged in the MD |
| 5 | Architectural significance unmeasured | No way to identify load-bearing components a priori; subsystem map alone misses density hotspots |

v3 closes these gaps with two new phases (Hotspot-Map, Cross-Cutting-Lenses), severity-overlay visualization, and a composable lens-library.

---

## 3. Pipeline (4 Phases)

```
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 0 — HEALTHCHECK              [existing, unchanged]       │
│   ├─ doc-drift (over primitive docs via /we:doc-improve)        │
│   ├─ bypass-register-drift (regenerate + diff committed)        │
│   └─ missing-primitive-scan (PR-churn + keyword hits)           │
├─────────────────────────────────────────────────────────────────┤
│  PHASE 1 — HOTSPOT MAP              [NEW]                       │
│   ├─ scripts/audit-hotspots.py — primitive-density score        │
│   ├─ classify Top-N: expected (documented hub) vs unexpected    │
│   └─ render diagrams/heatmap.mmd (quadrant: Prim × Churn)       │
├─────────────────────────────────────────────────────────────────┤
│  PHASE 2 — SUBSYSTEM DEEP-READ      [refined]                   │
│   PER subsystem in scope:                                       │
│   ├─ render diagrams/<id>.mmd (severity-overlay nach Findings)  │
│   │  └─ diff against previous → structural delta = MAJOR        │
│   ├─ default lens-bundle (7 lenses, each a documented checklist)│
│   │   plus extra_lens per subsystem (e.g. personality-cohesion) │
│   ├─ cross-reference Phase-1 hotspots within this subsystem     │
│   └─ each finding: severity + lens + file:line + fix + effort   │
├─────────────────────────────────────────────────────────────────┤
│  PHASE 3 — CROSS-CUTTING LENSES     [NEW]                       │
│   ├─ encapsulation-boundaries (exhaustive grep, not subsystem-bound)│
│   ├─ architectural-significance (Phase-1 hotspots, 4-question lens) │
│   ├─ doc-vs-reality-drift (each primitive-doc invariant verified)   │
│   └─ optional: personality-cohesion, privacy, gdpr, performance, cost │
├─────────────────────────────────────────────────────────────────┤
│  PHASE 4 — FINDINGS CONSOLIDATION   [refined]                   │
│   ├─ master.md with Executive Summary + 3 Intensity-Views:      │
│   │   1. severity-pie.mmd (CRIT/MAJ/MIN/NIT pie)                │
│   │   2. heatmap.mmd (Phase-1 quadrant)                         │
│   │   3. drift-matrix.mmd (Phase-3 doc-vs-reality)              │
│   └─ Reading-order recommendation                               │
└─────────────────────────────────────────────────────────────────┘
```

**Phase-skip-bility:** every phase can be skipped via CLI flag. The skill is composable — `/we:audit-architecture --hotspots-only` runs Phase 1 alone in ~10 seconds.

---

## 4. Phases in Detail

### Phase 0 — Healthcheck (unchanged from v2)

Three sanity checks, runnable as `--healthcheck-only` for fast pre-PR validation:

1. **Doc-drift** — invoke `/we:doc-improve` over `docs/architecture/primitives/*.md` (configured glob).
2. **Bypass-register-drift** — re-run `scripts/generate-bypass-register.sh`, diff against committed register.
3. **Missing-primitive-scan** — `scripts/scan-recent-primitives.sh` parses last N PRs for keyword hits + path churn.

Output is markdown ready to inline into the master findings MD. See `references/healthcheck.md`.

### Phase 1 — Hotspot Map (NEW)

For each Python file under the project's `backend_root`:

```
score = len(primitives_composed) × 5    # Platform Primitives via grep on surface symbols
      + LOC / 50                         # complexity proxy
      + churn (commits in window)        # recent activity
      + bypasses_count × 3               # # *-BYPASS-OK: knowing-divergence
      + private_reach_ins × 3            # imports of `<core_path>/_*` outside core
      + leak_count × 4                   # langchain/langgraph runtime imports outside core
```

Top-N sorted descending. Each entry then auto-classified:

- **Expected** if file path matches a `expected_hubs:` entry in YAML (documented density-hub).
- **Unexpected** otherwise.

Unexpected high-scorers are the candidates for Phase-3 architectural-significance deep-read.

Output:
- `<findings_dir>/<date>-hotspots.md` with Top-N table + Top-5 detailed primitive-composition
- `<diagrams_dir>/heatmap.mmd` (Mermaid quadrant chart, color = max-finding-severity if Phase 2 ran)

Method docs: `references/hotspot-density.md`, `references/architectural-significance.md`.

### Phase 2 — Subsystem Deep-Read (refined from v2)

Per subsystem in scope:

1. **Render Mermaid diagram** to `<diagrams_dir>/<id>.mmd`.
   - Read `architecture_docs:` + actual `paths:` to derive structure.
   - If a previous diagram exists, diff against it — structural changes (new/removed nodes or edges) become a MAJOR finding (`structural-drift`).
2. **Run lens checklist** — default 7 lenses + any `extra_lens:` configured for this subsystem:
   1. Kapselung (encapsulation)
   2. Schichten (layering)
   3. Primitive-Compliance (each documented invariant verified explicitly)
   4. Security & Multi-Tenancy
   5. Observability
   6. Error-Handling
   7. Tests (invariant-to-test mapping)
3. **Cross-reference Phase-1 hotspots** within the subsystem: any unexpectedly-dense file in this subsystem's path scope is flagged.
4. **Each finding** carries: severity (CRITICAL/MAJOR/MINOR/NIT), lens, file:line citation, fix proposal, effort estimate.

Output: `<findings_dir>/subsystems/<id>.md` per subsystem. Diagram embedded inline + linked to `.mmd`.

For `mode: docs_only` subsystems: render diagram only + invoke `/we:doc-improve` over the listed `architecture_docs`. No findings.

Method docs: `references/audit-checklist.md`.

### Phase 3 — Cross-Cutting Lenses (NEW)

These lenses span the whole codebase, ignoring subsystem boundaries:

**Always-active (cross_cutting in YAML):**

- **encapsulation-boundaries** — exhaustive grep for forbidden cross-module imports:
  - `from langchain*` / `from langgraph` outside designated homes (`companion/core/`, `config/llm.py`, `config/_instrumented_model.py`)
  - Reach-ins to `<core_path>/_*` private modules from outside the core path
  - Channel-as-THIN-transport rule: channels must not construct LangGraph types
- **architectural-significance** — for each Phase-1 unexpected hotspot, apply 4-question risk lens:
  1. **Coupling** — afferent fan-in count
  2. **Cohesion** — does it have a single responsibility?
  3. **Stability** — can it change without breaking dependents?
  4. **Testability** — isolated-testable, or only via integration?
- **doc-vs-reality-drift** — for each primitive-detail-doc with explicit invariants (`**I1.**`, `**I2.**`, etc.):
  1. Extract invariants (manual catalog OR `scripts/extract-invariants.py` if available)
  2. Verify each one in code via grep / read
  3. Verdict: ✓ (holds) | ⚠ (partial) | ✗ (violated) | ? (unverified)
  4. Render `drift-matrix.mmd` table-as-flowchart

**Opt-in (optional_lenses in YAML, activated via `--lens=`):**

- **personality-cohesion** (Companion-projects) — uses `personality_cohesion:` config block:
  - identity-construction sites are confined to `identity_construction_paths:`
  - 5-component-model: each component has exactly one canonical home in `five_components_map:`
  - `forbidden_outside_consciousness:` patterns must not appear outside `identity_construction_paths`
- **privacy** (data-residency) — already in v2 as `extra_lens: privacy` for plans-residency subsystem; promoted to a configurable cross-cutting lens
- **gdpr** (EU compliance) — placeholder spec, future work
- **performance** (high-throughput) — placeholder spec, future work
- **cost** (LLM-cost optimization) — placeholder spec, future work

Output: `<findings_dir>/cross-cutting.md`. Lens definitions: `references/encapsulation-boundaries.md`, `references/architectural-significance.md`, `references/doc-vs-reality-drift.md`, `references/personality-cohesion.md`.

### Phase 4 — Findings Consolidation (refined)

Aggregate all phases into a master MD:

**`<findings_dir>/<date>-<scope>/master.md`** — the entry-point.

```yaml
---
type: audit
domain: [...]
status: current
date: YYYY-MM-DD
scope: full | <id> | <id1>,<id2> | healthcheck | hotspots
phases: [0, 1, 2, 3, 4]   # which phases ran
lenses_used: [...]
---
```

Body:

1. **Executive Summary** — severity counts table, 3 intensity views inline
2. **Three intensity views** (each as Mermaid block + linked `.mmd`):
   - `severity-pie.mmd` — pie chart of finding counts
   - `heatmap.mmd` — Phase-1 quadrant
   - `drift-matrix.mmd` — Phase-3 doc-vs-reality matrix
3. **Reading order** — recommended order in which to read sub-files
4. **Findings index** — sorted by severity → lens → file
5. **Sub-file links** — `subsystems/`, `cross-cutting.md`, `hotspots.md`

The sub-files contain detail; master is the navigation surface.

Method doc: `references/findings-template.md`.

---

## 5. Lens Library Architecture

Lenses are composable units of audit logic. Each lens has:

```
references/<lens-name>.md   contains:
   ├─ Purpose (1-3 sentences)
   ├─ When to apply (config triggers + scope)
   ├─ Method (the actual checklist or grep patterns)
   ├─ Output format (per-finding template)
   └─ Examples (real findings from past audits)
```

**Lens registry** (in `references/lens-library.md`):

| Lens | Scope | Activation | Type |
|---|---|---|---|
| kapselung | per-subsystem | default | Phase 2 |
| schichten | per-subsystem | default | Phase 2 |
| primitive-compliance | per-subsystem | default | Phase 2 |
| security | per-subsystem | default | Phase 2 |
| observability | per-subsystem | default | Phase 2 |
| error-handling | per-subsystem | default | Phase 2 |
| tests | per-subsystem | default | Phase 2 |
| encapsulation-boundaries | project-wide | default | Phase 3 cross_cutting |
| architectural-significance | project-wide | default | Phase 3 cross_cutting |
| doc-vs-reality-drift | project-wide | default | Phase 3 cross_cutting |
| personality-cohesion | project-wide | opt-in | Phase 3 optional |
| privacy | per-subsystem OR project-wide | opt-in via `extra_lens` or `--lens=` | Phase 2 + Phase 3 |
| gdpr | project-wide | opt-in (future) | Phase 3 optional |
| performance | project-wide | opt-in (future) | Phase 3 optional |
| cost | project-wide | opt-in (future) | Phase 3 optional |

Adding a new lens = adding `references/<new-lens>.md` + registering it in `lens-library.md` + (if it needs config) defining the YAML schema.

---

## 6. YAML Config Schema (v3, backward-compatible with v2)

```yaml
# docs/.audit-architecture.yml — full v3 schema

# Output paths (existing, v2)
findings_dir: docs/audits/
diagrams_dir: docs/architecture/diagrams/

# NEW v3: backend root for hotspot scan (default: detect from project structure)
backend_root: apps/backend/app

# NEW v3: lens activation (all optional, skill default-loads if missing)
default_lenses: [kapselung, schichten, primitive-compliance, security, observability, error-handling, tests]
cross_cutting:  [encapsulation-boundaries, architectural-significance, doc-vs-reality-drift]
optional_lenses: [personality-cohesion, privacy]

# Phase 0 (existing, v2)
healthcheck:
  doc_drift:
    enabled: true
    target_glob: "docs/architecture/primitives/*.md"
  bypass_register_drift:
    enabled: true
    register_path: "docs/architecture/BYPASS-REGISTER.md"
    generator_script: "scripts/generate-bypass-register.sh"
  missing_primitive_scan:
    enabled: true
    pr_count: 100
    repo_paths: [apps/backend/app/]
    keyword_patterns: [introduce, centralize, wrapper, factory, "all .* go through", primitive]

# NEW v3: Phase 1 hotspot config
hotspots:
  top_n: 15
  since: "6 months ago"
  expected_hubs:                           # for expected/unexpected classification
    - apps/backend/app/main.py
    - apps/backend/app/companion/core/being.py
    # ... documented density hubs
  primitive_detectors_extra: {}            # project-specific overrides for primitives.default.yml
  encapsulation_homes:                     # used by encapsulation-boundaries lens
    langchain: [apps/backend/app/companion/core/, apps/backend/app/config/llm.py, apps/backend/app/config/_instrumented_model.py]
    langgraph: [apps/backend/app/companion/core/]
  private_module_root: apps/backend/app/companion/core   # used to detect _-prefix reach-ins

# NEW v3: Personality-Cohesion config (Companion-projects opt-in)
personality_cohesion:
  identity_construction_paths:
    - apps/backend/app/companion/core/consciousness.py
    - apps/backend/app/companion/core/_context_composer.py
  five_components_map:
    CONSCIOUSNESS: [apps/backend/app/companion/core/]
    SENSES:        [apps/backend/app/senses/]
    BODY:          [apps/backend/app/companion/channels/, apps/backend/app/tools/]
    MEMORY:        [apps/backend/app/companion/core/memory.py, apps/backend/app/crud/memory.py]
    EXPERIENCE:    [apps/backend/app/services/evolution/]
  forbidden_outside_consciousness:
    - "system_prompt ="
    - "personality ="

# Subsystems (existing v2 schema, extended with optional extra_lens)
subsystems:
  - id: companion-core
    name: "Companion Core"
    mode: deep-audit                          # or docs_only
    architecture_docs: [COMPANION-CORE.md, CONSCIOUSNESS.md]
    primitives: [companion-gateway-being, langgraph-checkpointer]
    paths: [apps/backend/app/companion/core/, apps/backend/app/companion/gateway/]
    extra_lens: [personality-cohesion]        # NEW v3: zieht Lens auch in Phase-2-Subsystem
```

**Backward compatibility:** every v3 field is optional. v2 configs work unchanged — defaults are loaded by the skill.

---

## 7. Output Directory Structure

```
<findings_dir>/<date>-<scope>/
├── master.md                  # Executive Summary + reading-order + index
├── hotspots.md                # Phase 1 output
├── cross-cutting.md           # Phase 3 output
└── subsystems/
    ├── <id1>.md               # Phase 2 per-subsystem
    └── <id2>.md

<diagrams_dir>/
├── severity-pie.mmd           # Phase 4
├── heatmap.mmd                # Phase 1 / Phase 4
├── drift-matrix.mmd           # Phase 3 / Phase 4
└── <id>.mmd                   # Phase 2 per-subsystem (severity-overlaid)
```

Filename rules (`<scope>` part):
- full run → `full`
- single subsystem → its `id`
- multiple → comma-joined `<id1>-<id2>`
- `--healthcheck-only` → `healthcheck`
- `--hotspots-only` → `hotspots`

---

## 8. Severity & Visualization

Standardized in `references/visualization.md`. Severity classes are written into every Mermaid diagram via `classDef`:

```
CRITICAL  →  classDef critical fill:#ffcccc, stroke:#cc0000, stroke-width:3px
MAJOR     →  classDef major    fill:#ffe0b3, stroke:#ff9900, stroke-width:2px
MINOR     →  classDef minor    fill:#fff5cc, stroke:#cc9900
NIT       →  classDef nit      fill:#eee,    stroke:#999
CLEAN     →  classDef clean    fill:#ccffcc, stroke:#00aa00
```

Subsystem-Audit-Diagramme apply these classes to nodes that have findings — the visual scan reveals where it burns.

The 3 intensity charts in master.md:

1. **Severity Pie** — `pie title Findings by Severity \n "CRITICAL" : N \n ...`
2. **Hotspot Quadrant** — Mermaid `quadrantChart`, X = primitive count, Y = churn, color = max-severity
3. **Drift Matrix** — Mermaid `flowchart TB` table-as-grid, classes ✓/⚠/✗/?

---

## 9. CLI Surface

```
/we:audit-architecture                                   # full run (all phases)
/we:audit-architecture <id>[,<id2>,…]                    # scoped subsystems
/we:audit-architecture --healthcheck-only                # only Phase 0
/we:audit-architecture --hotspots-only                   # only Phase 1
/we:audit-architecture --skip-phase=0,3                  # selective skip
/we:audit-architecture --lens=encapsulation-boundaries   # only this cross-cutting lens (Phase 3)
/we:audit-architecture --since=YYYY-MM-DD                # delta — only subsystems changed since
```

Combinations are valid: `--lens=personality-cohesion --skip-phase=2` runs only Phase 1+3+4 with the personality lens activated.

---

## 10. Backward Compatibility

**v2 → v3 migration is config-only and optional.**

- Existing v2 `.audit-architecture.yml` files run on v3 unchanged. The skill default-loads any missing v3 sections.
- v2 outputs `<findings_dir>/<date>-<scope>.md` (single file). v3 writes a directory `<findings_dir>/<date>-<scope>/` with `master.md` + sub-files. v3 keeps a top-level `<date>-<scope>.md` symlink/redirect so existing links continue to work.
- v2 CLI flags (`--healthcheck-only`, `--skip-healthcheck`, `--since`, `<id>`) all work in v3 with identical semantics.
- v3 new flags (`--hotspots-only`, `--skip-phase`, `--lens`) are additive.

---

## 11. Future Work / Open Questions

1. **`/playground:playground` integration** — Phase 4 could optionally hand the `.mmd` files to `/playground:playground` for an interactive HTML dashboard. Spec hook only; implementation is a future PR.
2. **Auto-extraction of invariants** — `references/doc-vs-reality-drift.md` defines the manual extraction pattern for v3. Future iteration: `scripts/extract-invariants.py` parses primitive-docs for `**I<N>.**` patterns automatically.
3. **Additional optional lenses** — `gdpr`, `performance`, `cost` are placeholder entries in the lens registry. Each future addition follows the same pattern: write `references/<lens>.md`, register in `lens-library.md`, define YAML config block if needed.
4. **Multi-language support** — script-side patterns are Python-specific (`apps/backend/app/`). For a TypeScript or Go backend, `primitive_detectors_extra` would carry the language-specific regex set. Spec already supports this via the YAML override; verification is a future test.
5. **Diff-aware delta-mode** — `--since=DATE` only re-audits subsystems whose `paths:` changed. v3 spec leaves the implementation to SKILL.md (git diff filter) but does not add a script.

---

## 12. References

- v2 design (implicit): `we/skills/audit-architecture/SKILL.md` v2.19.0
- Plugin convention: `we/skills/doc-improve/SKILL.md` (similar phase-based
  dispatcher pattern)
- Companion-Anatomy: the personality-cohesion lens assumes a "5 components
  of a companion" shape (CONSCIOUSNESS / SENSES / BODY / MEMORY /
  EXPERIENCE). Projects that ship Companion runtimes typically have an
  internal architecture doc describing this; the lens is opt-in via
  `default_lenses` / `optional_lenses`.
