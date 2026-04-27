---
name: audit-architecture
description: Run a multi-phase backend architecture audit. Phases (Healthcheck → Hotspot-Map → Subsystem-Deep-Read → Cross-Cutting-Lenses → Findings) are skip-bar, lenses are composable, severity-tagged findings produce visual-intensity diagrams. Use when user types "/we:audit-architecture" or asks to "audit the backend architecture", "check architectural drift", "run an architecture review", "find architectural problem zones". Output is a directory of dated findings plus Mermaid diagrams committed to the project.
---

# /we:audit-architecture — Backend Architecture Audit (v3)

Multi-phase audit that surfaces architectural problem zones across **subsystem boundaries** (Phase 1 hotspot map), **conceptual cohesion** (Phase 3 lenses), and **doc-vs-reality drift** (Phase 3) — not just per-subsystem checklist runs. Each phase is independently runnable; the skill is a hammer that can also be a tweezers.

**For the canonical architecture spec, read [`SPEC-v3.md`](SPEC-v3.md).**

---

## CLI Surface

```
/we:audit-architecture                                   # full run (all phases)
/we:audit-architecture <id>[,<id2>,…]                    # scoped subsystems
/we:audit-architecture --healthcheck-only                # only Phase 0
/we:audit-architecture --hotspots-only                   # only Phase 1
/we:audit-architecture --skip-phase=N[,M]                # skip listed phases (0..4)
/we:audit-architecture --skip-healthcheck                # alias for --skip-phase=0
/we:audit-architecture --lens=name1,name2                # restrict Phase 3 to listed lenses
/we:audit-architecture --since=YYYY-MM-DD                # delta — only subsystems with changes
```

`<id>` matches the `id:` field from `docs/.audit-architecture.yml`. CLI flags compose: `--lens=personality-cohesion --skip-phase=2` runs only Phase 1+3+4 with the personality lens.

---

## Bootstrap

Before any phase, load the project config and the lens library:

1. Read `docs/.audit-architecture.yml` from repo root. If missing, tell the user to create one and point at `references/subsystems.md` for the schema.
2. Read [`references/subsystems.md`](references/subsystems.md) to understand the schema (and apply v3 default-loading for missing sections — see `subsystems.md` § "Reading the YAML at Run-Time").
3. Read [`references/lens-library.md`](references/lens-library.md) for the lens registry. Cross-check: every lens in `default_lenses`, `cross_cutting`, `optional_lenses`, and per-subsystem `extra_lens:` must have a corresponding `references/<lens-name>.md`.
4. Determine which phases to run based on CLI flags:
   - `--healthcheck-only` → only Phase 0
   - `--hotspots-only` → only Phase 1
   - `--skip-phase=...` → skip listed phases
   - `--skip-healthcheck` → equivalent to `--skip-phase=0`
   - default: all phases
5. Determine output paths: `<findings_dir>/<date>-<scope>/` (directory layout, see `findings-template.md`).

---

## Phase 0 — Healthcheck

Read [`references/healthcheck.md`](references/healthcheck.md). Three checks (each toggleable via YAML's `healthcheck.<check>.enabled`):

1. **Doc-Drift** — invoke `/we:doc-improve` over the configured `target_glob`.
2. **Bypass-Register-Drift** — re-run the generator script, diff against committed register.
3. **Missing-Primitive-Scan** — call `scripts/scan-recent-primitives.sh` with the project's config.

Output: section under `## Healthcheck` in `<findings_dir>/<date>-<scope>/master.md`.

If `--healthcheck-only`: write only this section into master.md and exit. Filename: `<date>-healthcheck/master.md` plus a backward-compat redirect at `<date>-healthcheck.md`.

---

## Phase 1 — Hotspot Map

Read [`references/hotspot-density.md`](references/hotspot-density.md). Run the script:

```bash
python3 <skill_root>/scripts/audit-hotspots.py \
  --project-config <repo_root>/docs/.audit-architecture.yml \
  --primitives-catalog <skill_root>/scripts/primitives.default.yml \
  --top <hotspots.top_n or 15> \
  --since "<hotspots.since or '6 months ago'>" \
  --write
```

Outputs:

- `<findings_dir>/<date>-<scope>/hotspots.md` (or `<date>-hotspots/master.md` if `--hotspots-only`)
- `<diagrams_dir>/heatmap.mmd` (Mermaid quadrant chart, see `references/visualization.md`)

The script computes the score formula and classifies each top-N entry as **expected** (in `expected_hubs:`) or **unexpected**. Unexpected hotspots feed Phase 3's `architectural-significance` lens.

If `--hotspots-only`: stop here.

---

## Phase 2 — Subsystem Deep-Read

Read [`references/audit-checklist.md`](references/audit-checklist.md). For each subsystem with `mode: deep-audit` (filtered by CLI scope):

1. **Render Mermaid diagram** to `<diagrams_dir>/<id>.mmd`:
   - Source: the listed `architecture_docs` + actual `paths:`
   - Apply severity-overlay classes per `references/visualization.md`
   - If a previous version exists in git, run **diff-against-previous** check (see `audit-checklist.md` § Diff)
2. **Run the lens checklist:**
   - All lenses in `default_lenses` (the standard 7)
   - Plus any in subsystem's `extra_lens:` (e.g., `personality-cohesion`)
   - Plus the **diff-against-previous-diagram** check
3. **Cross-reference Phase-1 hotspots:** any file in this subsystem's `paths:` that was an unexpected hotspot in Phase 1 → surface as cross-reference (see `audit-checklist.md` § Cross-Reference).
4. **Collect findings** with severity + lens + file:line citation + fix proposal + effort estimate. Use the template in `references/findings-template.md` § Per-Finding Template.

Write per-subsystem findings to `<findings_dir>/<date>-<scope>/subsystems/<id>.md`.

For subsystems with `mode: docs_only`:

- Render diagram (or drift-check if exists)
- Invoke `/we:doc-improve` over the listed `architecture_docs`
- Output: `<findings_dir>/<date>-<scope>/subsystems/<id>.md` with Doku-Refresh proposals, no findings

---

## Phase 3 — Cross-Cutting Lenses

Read each activated lens's reference doc:

**Always-active (in `cross_cutting:`):**

- [`references/encapsulation-boundaries.md`](references/encapsulation-boundaries.md) — exhaustive grep for vendor leaks + private reach-ins
- [`references/architectural-significance.md`](references/architectural-significance.md) — 4-question risk lens applied to each unexpected Phase-1 hotspot
- [`references/doc-vs-reality-drift.md`](references/doc-vs-reality-drift.md) — verify each primitive-doc invariant in code, render drift-matrix

**Opt-in (only if in `optional_lenses` AND activated via `--lens=` or per-subsystem `extra_lens:`):**

- [`references/personality-cohesion.md`](references/personality-cohesion.md) — Companion-as-Person verification
- Privacy lens: see `references/audit-checklist.md` § Privacy-Lens

For each activated lens, follow its method section. Each lens produces 0..N findings using the template in `references/findings-template.md` § Per-Finding Template.

If `--lens=name1,name2`: only run the listed lenses (overrides `cross_cutting`).

Write all Phase-3 findings to `<findings_dir>/<date>-<scope>/cross-cutting.md` (one section per lens).

---

## Phase 4 — Findings Consolidation

Read [`references/findings-template.md`](references/findings-template.md) for the master.md skeleton. Write `<findings_dir>/<date>-<scope>/master.md` containing:

1. **Frontmatter** — `type: audit`, scope, date, phases, lenses_used
2. **Executive Summary** — severity counts table
3. **Three intensity views (inline Mermaid + file links):**
   - `severity-pie.mmd` — pie chart of finding counts
   - `heatmap.mmd` — Phase-1 quadrant (only if Phase 1 ran)
   - `drift-matrix.mmd` — Phase-3 doc-vs-reality matrix (only if that lens ran)
4. **Reading-order recommendation**
5. **Findings index** — sorted: severity → lens → file
6. **Sub-file links** — to subsystems/*, cross-cutting.md, hotspots.md
7. **Open items from previous audits** (scan `<findings_dir>/` for older audits)

Generate the three intensity diagrams in `<diagrams_dir>/`:

- `severity-pie.mmd` — populate counts
- `heatmap.mmd` — populated by Phase 1 already; in Phase 4, optionally re-color nodes by max-severity-finding from Phase 2
- `drift-matrix.mmd` — populated by Phase 3 doc-vs-reality lens

Write a backward-compat redirect at `<findings_dir>/<date>-<scope>.md` (top-level) pointing to the new master.md (see `findings-template.md` § Backward Compatibility).

---

## What NOT to do

- **Don't auto-fix findings.** Output is recommendation; user decides.
- **Don't commit anything besides** the diagrams in `<diagrams_dir>/` and the findings directory `<findings_dir>/<date>-<scope>/`.
- **Don't bypass the project's `.audit-architecture.yml`** — if the YAML is missing, point at `references/subsystems.md` and ask the user to create one.
- **Don't invent subsystems** not in the YAML. The YAML is the source of truth for scope.
- **Don't run a lens** that doesn't have a corresponding `references/<lens-name>.md`. If the YAML lists an unknown lens name, error out with the available-lens list.
- **Don't compute Phase 1 with a primitive catalog you don't have.** If `scripts/primitives.default.yml` is missing AND the project doesn't define `primitive_detectors:`, error out (the score would be density-only, not informative).
- **Don't skip the diff-against-previous check** when a previous diagram exists — structural drift is one of the highest-signal findings.

---

## Backward Compatibility (v2 → v3)

The skill remains backward-compatible with v2 configs:

- v2 `extra_lens: privacy` (string) → coerced to `[privacy]` (list) internally
- v2 configs missing `default_lenses`, `cross_cutting`, `optional_lenses` → skill default-loads
- v2 configs missing `hotspots:` block → Phase 1 runs with skill defaults (top_n=15, since=6mo, no expected_hubs)
- v2 output path `<date>-<scope>.md` (single file) → v3 writes a redirect file pointing to `<date>-<scope>/master.md`

To opt INTO v3 features, the project YAML adds optional sections — see `references/subsystems.md` § Migration from v2 to v3.

---

## Output Reference

Final layout per run:

```
<findings_dir>/<date>-<scope>/
├── master.md                  # Phase 4 entry point
├── hotspots.md                # Phase 1 (always present unless --skip-phase=1)
├── cross-cutting.md           # Phase 3 (present if any lens ran)
└── subsystems/
    ├── <id1>.md               # Phase 2 per subsystem
    └── <id2>.md

<diagrams_dir>/
├── severity-pie.mmd           # Phase 4
├── heatmap.mmd                # Phase 1, Phase 4 may recolor
├── drift-matrix.mmd           # Phase 3
└── <id>.mmd                   # Phase 2 per subsystem
```

Plus the backward-compat redirect at `<findings_dir>/<date>-<scope>.md`.

---

## References

- [`SPEC-v3.md`](SPEC-v3.md) — canonical architecture spec
- [`references/subsystems.md`](references/subsystems.md) — YAML schema
- [`references/lens-library.md`](references/lens-library.md) — lens registry + activation rules
- [`references/healthcheck.md`](references/healthcheck.md) — Phase 0
- [`references/hotspot-density.md`](references/hotspot-density.md) — Phase 1
- [`references/audit-checklist.md`](references/audit-checklist.md) — Phase 2
- [`references/encapsulation-boundaries.md`](references/encapsulation-boundaries.md) — Phase 3 lens
- [`references/architectural-significance.md`](references/architectural-significance.md) — Phase 3 lens
- [`references/doc-vs-reality-drift.md`](references/doc-vs-reality-drift.md) — Phase 3 lens
- [`references/personality-cohesion.md`](references/personality-cohesion.md) — Phase 3 opt-in lens
- [`references/findings-template.md`](references/findings-template.md) — Phase 4 output skeleton
- [`references/visualization.md`](references/visualization.md) — Mermaid templates + severity-CSS
- [`scripts/audit-hotspots.py`](scripts/audit-hotspots.py) — Phase 1 implementation
- [`scripts/scan-recent-primitives.sh`](scripts/scan-recent-primitives.sh) — Phase 0 implementation
- [`scripts/primitives.default.yml`](scripts/primitives.default.yml) — default primitive-detector catalog
