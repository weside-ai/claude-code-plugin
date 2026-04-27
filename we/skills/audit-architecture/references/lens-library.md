---
name: audit-architecture-lens-library
description: Composable lens architecture for /we:audit-architecture v3 — registry of all lenses, activation rules, and how to add new ones
type: reference
---

# Lens Library

Lenses are composable units of audit logic. Each lens answers one question. The skill picks lenses by phase + scope; the user can override via CLI flags or per-subsystem `extra_lens:` in YAML.

## Lens Registry

| Lens | Scope | Activation | Phase | Reference |
|---|---|---|---|---|
| kapselung | per-subsystem | default | 2 | `audit-checklist.md` |
| schichten | per-subsystem | default | 2 | `audit-checklist.md` |
| primitive-compliance | per-subsystem | default | 2 | `audit-checklist.md` |
| security | per-subsystem | default | 2 | `audit-checklist.md` |
| observability | per-subsystem | default | 2 | `audit-checklist.md` |
| error-handling | per-subsystem | default | 2 | `audit-checklist.md` |
| tests | per-subsystem | default | 2 | `audit-checklist.md` |
| encapsulation-boundaries | project-wide | default | 3 cross_cutting | `encapsulation-boundaries.md` |
| architectural-significance | project-wide | default | 3 cross_cutting | `architectural-significance.md` |
| doc-vs-reality-drift | project-wide | default | 3 cross_cutting | `doc-vs-reality-drift.md` |
| personality-cohesion | project-wide | opt-in | 3 optional | `personality-cohesion.md` |
| privacy | per-subsystem OR project-wide | opt-in | 2 (`extra_lens`) or 3 (`--lens=`) | `audit-checklist.md` § Privacy |
| gdpr | project-wide | opt-in | 3 optional (future) | TBD |
| performance | project-wide | opt-in | 3 optional (future) | TBD |
| cost | project-wide | opt-in | 3 optional (future) | TBD |

## Activation Rules

**default lenses** run automatically in their phase. Configured in YAML:

```yaml
default_lenses: [kapselung, schichten, primitive-compliance, security, observability, error-handling, tests]
cross_cutting:  [encapsulation-boundaries, architectural-significance, doc-vs-reality-drift]
```

If these YAML keys are missing, the skill default-loads the values above (backward-compat with v2 configs).

**opt-in lenses** require explicit activation:

- Per-subsystem: `extra_lens: [name1, name2]` in the subsystem entry. Lens runs in Phase 2 alongside the default lenses for that subsystem.
- Project-wide: `--lens=name1,name2` CLI flag. Lens runs in Phase 3 across the whole codebase.

```yaml
optional_lenses: [personality-cohesion, privacy]   # available for opt-in
```

Listing a lens in `optional_lenses:` makes it available; it does NOT run unless explicitly activated.

## CLI Combinators

```bash
# default run: all default + all cross_cutting lenses
/we:audit-architecture

# subsystem with extra lens
/we:audit-architecture companion-core
# (uses extra_lens: [personality-cohesion] from YAML if configured)

# explicit cross-cutting lens, skip Phase 2
/we:audit-architecture --lens=personality-cohesion --skip-phase=2

# Phase 1 only — get the hotspot map without findings work
/we:audit-architecture --hotspots-only
```

## Per-Lens Documentation Format

Each lens has a dedicated reference file (`references/<lens-name>.md`) with this structure:

```markdown
---
name: audit-architecture-<lens-name>
description: <1-line>
type: reference
---

# <Lens Name>

## Purpose
1-3 sentences: what question this lens answers.

## When to apply
- Phase X (default | opt-in)
- Scope: per-subsystem | project-wide
- Trigger: how the user activates it (YAML / CLI / extra_lens)
- Project requirements: what the project must have for the lens to be useful

## Method
The actual checklist or grep patterns. Concrete enough that the skill can execute it.
For grep-driven lenses: list the patterns + their meaning.
For checklist lenses: number the questions + what evidence to look for.

## Output format
Per-finding template specific to this lens (severity tag, citation style, fix proposal shape).

## Examples
1-3 real findings from past audits, with file:line citations.
```

## Adding a New Lens

1. Decide scope (per-subsystem vs project-wide) and activation (default vs opt-in).
2. Write `references/<new-lens>.md` following the format above.
3. Register it in this file's table.
4. If the lens needs config (paths, patterns, etc.), document the YAML schema block in `subsystems.md`.
5. Add an example finding to the lens reference (real or hypothetical).
6. If the lens has a script/regex helper, place it under `scripts/` and document the CLI.

## Lens vs Phase: clarification

- **Phase** = what the skill DOES (Healthcheck, Hotspot-Map, Subsystem-Read, Cross-Cutting, Consolidation).
- **Lens** = what the skill LOOKS THROUGH (a specific question + method).

A lens runs IN a phase. The default 7 Phase-2 lenses are the same regardless of which subsystem is being audited; what varies is the `extra_lens:` per subsystem. Phase-3 lenses are project-wide and can be selectively disabled or expanded via CLI.

## Backward Compatibility (v2 → v3)

v2 had a fixed 7-lens checklist plus an `extra_lens: privacy` flag for the plans-residency subsystem. v3 generalizes:

- The 7 lenses become `default_lenses:` (still default-loaded if YAML omits them)
- `extra_lens:` per subsystem is unchanged in syntax; it now supports any registered lens name
- `cross_cutting:` and `optional_lenses:` are NEW v3 sections; absent in v2 configs, default-loaded by the skill
