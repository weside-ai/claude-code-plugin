---
name: audit-architecture-spec-v3
description: Design rationale for the v3 rewrite of the /we:audit-architecture skill — goals, why-v3, future work. Maintainer doc, not loaded at runtime; the operational surface lives in SKILL.md and the references (see the owner table).
type: reference
---

# SPEC v3 — `/we:audit-architecture`

**Status:** Shipped (v2.20.0+ of the `we` plugin).
**Audience:** Skill maintainers. This file carries the *why*; everything operational has exactly
one owner elsewhere — see the table at the end. Do not restate owned material here.

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

## 3. Future Work / Open Questions

1. **`/playground:playground` integration** — Phase 4 could optionally hand the `.mmd` files to `/playground:playground` for an interactive HTML dashboard. Spec hook only; implementation is a future PR.
2. **Auto-extraction of invariants** — `references/doc-vs-reality-drift.md` defines the manual extraction pattern for v3. Future iteration: `scripts/extract-invariants.py` parses primitive-docs for `**I<N>.**` patterns automatically.
3. **Additional optional lenses** — `gdpr`, `performance`, `cost` are placeholder entries in the lens registry. Each future addition follows the same pattern: write `references/<lens>.md`, register in `lens-library.md`, define YAML config block if needed.
4. **Multi-language support** — script-side patterns are Python-specific. For a TypeScript or Go backend, the project's `primitive_detectors` block (see `references/hotspot-density.md`) would carry the language-specific regex set; verification is a future test.
5. **Diff-aware delta-mode** — `--since=DATE` only re-audits subsystems whose `paths:` changed. Implementation lives in SKILL.md (git diff filter); no script added.

---

## 4. Owner Table (where the operational surface lives)

Single-owner rule: each of these is defined exactly once, there — this spec does not restate them.

| Surface | Owner |
|---|---|
| CLI flags + phase pipeline (Phases 0–4, skip semantics) | `SKILL.md` |
| Phase-0 healthcheck mechanics (incl. optional Graph-Drift check) | `references/healthcheck.md` |
| Hotspot score formula + config keys (`primitive_detectors`, `expected_hubs`, …) | `scripts/audit-hotspots.py` (formula) + `references/hotspot-density.md` (method) |
| Lens registry + activation rules | `references/lens-library.md` |
| Per-lens method + examples | `references/<lens-name>.md` |
| YAML config schema (v3, incl. v2 back-compat defaults) | `references/subsystems.md` |
| Output directory layout + master.md skeleton + v2 redirect | `references/findings-template.md` |
| Severity classDefs + Mermaid intensity views | `references/visualization.md` |
| Backward compatibility (v2 → v3) | `SKILL.md` § Backward Compatibility |

---

## 5. Historical References

- v2 design (implicit): `we/skills/audit-architecture/SKILL.md` v2.19.0
- Plugin convention: `we/skills/doc-improve/SKILL.md` (similar phase-based dispatcher pattern)
- Companion-Anatomy: the personality-cohesion lens assumes a "5 components of a companion" shape (CONSCIOUSNESS / SENSES / BODY / MEMORY / EXPERIENCE). Projects that ship Companion runtimes typically have an internal architecture doc describing this; the lens is opt-in.
